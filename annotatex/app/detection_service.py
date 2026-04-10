"""Real-time detection service for VisionQ.

Two input modes:
  HTTP — Runs a Flask HTTP server. Accepts POST /detect with multipart form-data (3-5 images).
  RTSP — Connects to an IP camera via RTSP, pulls frames continuously.

In both modes YOLO inference is run, direction is determined, and results are pushed
to the configured output URL.  Multiple named service instances can run simultaneously.
"""
from __future__ import annotations

import io
import json
import os
import socket
import threading
import time
import logging
from collections import deque
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Optional, Callable

import numpy as np
import requests
from PIL import Image

log = logging.getLogger("detection_service")

_PERSIST_PATH = os.path.expanduser("~/.visionq_services.json")
_MAX_LOG = 50


# ── Config dataclass ────────────────────────────────────────────────────────────

@dataclass
class ServiceConfig:
    name: str
    model_path: str
    # HTTP listen (used when rtsp_enabled=False)
    input_host: str
    input_port: int
    # Result push destination (both modes)
    output_host: str
    output_port: int
    auto_start: bool = False
    # RTSP source (used when rtsp_enabled=True)
    rtsp_enabled: bool = False
    rtsp_user: str = ""
    rtsp_password: str = ""
    rtsp_ip: str = ""
    rtsp_port: int = 554
    rtsp_channel: str = "Streaming/Channels/102"
    rtsp_interval: float = 0.5   # seconds between frame grabs

    @property
    def rtsp_url(self) -> str:
        auth = f"{self.rtsp_user}:{self.rtsp_password}@" if self.rtsp_user else ""
        channel = self.rtsp_channel.lstrip("/")
        return f"rtsp://{auth}{self.rtsp_ip}:{self.rtsp_port}/{channel}"

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @staticmethod
    def from_dict(d: dict) -> "ServiceConfig":
        return ServiceConfig(
            name=d["name"],
            model_path=d["model_path"],
            input_host=d.get("input_host", "0.0.0.0"),
            input_port=d["input_port"],
            output_host=d.get("output_host", "127.0.0.1"),
            output_port=d["output_port"],
            auto_start=d.get("auto_start", False),
            rtsp_enabled=d.get("rtsp_enabled", False),
            rtsp_user=d.get("rtsp_user", ""),
            rtsp_password=d.get("rtsp_password", ""),
            rtsp_ip=d.get("rtsp_ip", ""),
            rtsp_port=d.get("rtsp_port", 554),
            rtsp_channel=d.get("rtsp_channel", "Streaming/Channels/102"),
            rtsp_interval=d.get("rtsp_interval", 0.5),
        )


def load_saved_configs() -> list[ServiceConfig]:
    try:
        with open(_PERSIST_PATH, "r") as f:
            data = json.load(f)
        return [ServiceConfig.from_dict(d) for d in data]
    except Exception:
        return []


def save_configs(configs: list[ServiceConfig]):
    try:
        with open(_PERSIST_PATH, "w") as f:
            json.dump([c.to_dict() for c in configs], f, indent=2)
    except Exception as e:
        log.warning(f"Failed to save service configs: {e}")


# ── Port availability check ────────────────────────────────────────────────────

def is_port_free(host: str, port: int) -> bool:
    bind_host = "127.0.0.1" if host in ("0.0.0.0", "") else host
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((bind_host, port))
        return True
    except OSError:
        return False


# ── Direction logic ────────────────────────────────────────────────────────────

def _bbox_area(box) -> float:
    x1, y1, x2, y2 = box.xyxy[0].tolist()
    return (x2 - x1) * (y2 - y1)


def _largest_box(result):
    if result.boxes is None or len(result.boxes) == 0:
        return None
    return max(result.boxes, key=lambda b: _bbox_area(b))


def _determine_direction(areas: list[float]) -> str:
    if len(areas) < 2:
        return "unknown"
    n = len(areas)
    x = list(range(n))
    x_mean = sum(x) / n
    y_mean = sum(areas) / n
    numerator = sum((x[i] - x_mean) * (areas[i] - y_mean) for i in range(n))
    denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
    if denominator == 0:
        return "unknown"
    slope = numerator / denominator
    threshold = y_mean * 0.01
    if slope > threshold:
        return "forward"
    elif slope < -threshold:
        return "backward"
    return "unknown"


# ── Request log entry ──────────────────────────────────────────────────────────

@dataclass
class LogEntry:
    timestamp: str
    car_detected: bool
    direction: str
    confidence: float
    frames: int
    error: str = ""

    @staticmethod
    def from_result(payload: dict) -> "LogEntry":
        return LogEntry(
            timestamp=datetime.now().strftime("%H:%M:%S"),
            car_detected=payload.get("car_detected", False),
            direction=payload.get("direction", "unknown"),
            confidence=payload.get("confidence", 0.0),
            frames=payload.get("frames_analyzed", 0),
        )

    @staticmethod
    def from_error(msg: str) -> "LogEntry":
        return LogEntry(
            timestamp=datetime.now().strftime("%H:%M:%S"),
            car_detected=False,
            direction="",
            confidence=0.0,
            frames=0,
            error=msg,
        )

    def __str__(self) -> str:
        if self.error:
            return f"[{self.timestamp}]  ERROR: {self.error}"
        detected = "CAR" if self.car_detected else "no car"
        return (
            f"[{self.timestamp}]  {detected}"
            + (f"  {self.direction}  conf={self.confidence:.2f}  frames={self.frames}"
               if self.car_detected else f"  frames={self.frames}")
        )


# ── Flask app factory (HTTP mode) ──────────────────────────────────────────────

def _make_flask_app(
    service_name: str,
    model_holder: dict,
    output_url: Optional[str],
    log_callback: Callable[[LogEntry], None],
):
    from flask import Flask, request, jsonify
    app = Flask(f"detection_service_{service_name}")
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    @app.route("/detect", methods=["POST"])
    def detect():
        model = model_holder.get("model")
        if model is None:
            entry = LogEntry.from_error("Model not loaded")
            log_callback(entry)
            return jsonify({"error": "Model not loaded"}), 503

        files = request.files.getlist("images")
        if not files:
            entry = LogEntry.from_error("No images provided")
            log_callback(entry)
            return jsonify({"error": "No images provided"}), 400

        areas: list[float] = []
        confidences: list[float] = []
        car_detected = False

        for f in files:
            try:
                img = Image.open(io.BytesIO(f.read())).convert("RGB")
                img_np = np.array(img)
            except Exception as e:
                log.warning(f"Failed to decode image: {e}")
                continue

            results = model(img_np, verbose=False)
            if not results:
                continue

            result = results[0]
            box = _largest_box(result)
            if box is not None:
                car_detected = True
                areas.append(_bbox_area(box))
                confidences.append(float(box.conf[0]))

        direction = _determine_direction(areas) if car_detected else "unknown"
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        payload = {
            "service_name": service_name,
            "car_detected": car_detected,
            "direction": direction,
            "confidence": round(avg_confidence, 4),
            "frames_analyzed": len(files),
            "frames_with_car": len(areas),
        }

        log_callback(LogEntry.from_result(payload))

        if output_url:
            try:
                requests.post(output_url, json=payload, timeout=2)
            except Exception:
                pass  # output server not running — silently skip

        return jsonify(payload)

    @app.route("/status", methods=["GET"])
    def status():
        model = model_holder.get("model")
        return jsonify({
            "running": True,
            "service_name": service_name,
            "model_loaded": model is not None,
        })

    return app


# ── Service instance ────────────────────────────────────────────────────────────

STATE_STOPPED = "stopped"
STATE_LOADING = "loading"
STATE_RUNNING = "running"
STATE_ERROR   = "error"


class DetectionService:
    """Manages a single detection service (HTTP or RTSP mode)."""

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._server = None
        self._model_holder: dict = {"model": None}
        self._config: Optional[ServiceConfig] = None
        self._state: str = STATE_STOPPED
        self._error_msg: str = ""
        self._request_log: deque[LogEntry] = deque(maxlen=_MAX_LOG)
        self._log_lock = threading.Lock()
        self._stop_event = threading.Event()
        # Rolling buffer of bbox areas for direction tracking (RTSP mode)
        self._area_buffer: deque[float] = deque(maxlen=8)
        self._on_state_change: Optional[Callable[[], None]] = None

    @property
    def state(self) -> str:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state == STATE_RUNNING

    @property
    def is_loading(self) -> bool:
        return self._state == STATE_LOADING

    @property
    def error_msg(self) -> str:
        return self._error_msg

    @property
    def config(self) -> Optional[ServiceConfig]:
        return self._config

    def get_log_entries(self) -> list[LogEntry]:
        with self._log_lock:
            return list(self._request_log)

    def _append_log(self, entry: LogEntry):
        with self._log_lock:
            self._request_log.append(entry)

    def start_async(self, cfg: ServiceConfig, on_done: Callable[[str], None]):
        if self._state == STATE_RUNNING:
            on_done("Service is already running.")
            return
        if self._state == STATE_LOADING:
            on_done("Service is already loading.")
            return

        self._state = STATE_LOADING
        self._error_msg = ""
        self._config = cfg
        self._area_buffer.clear()

        def _worker():
            error = self._do_start(cfg)
            if error:
                self._state = STATE_ERROR
                self._error_msg = error
            else:
                self._state = STATE_RUNNING
            on_done(error)

        t = threading.Thread(target=_worker, daemon=True, name=f"StartWorker-{cfg.name}")
        t.start()

    def _do_start(self, cfg: ServiceConfig) -> str:
        if cfg.rtsp_enabled:
            return self._do_start_rtsp(cfg)
        return self._do_start_http(cfg)

    # ── HTTP mode ──────────────────────────────────────────────────────────────

    def _do_start_http(self, cfg: ServiceConfig) -> str:
        try:
            from ultralytics import YOLO
            model = YOLO(cfg.model_path)
            self._model_holder["model"] = model
        except Exception as e:
            return f"Failed to load model: {e}"

        output_url = (
            f"http://{cfg.output_host}:{cfg.output_port}/result"
            if cfg.output_host.strip() else None
        )
        app = _make_flask_app(cfg.name, self._model_holder, output_url, self._append_log)

        from werkzeug.serving import make_server
        try:
            self._server = make_server(cfg.input_host, cfg.input_port, app)
        except Exception as e:
            self._model_holder["model"] = None
            return f"Failed to bind to {cfg.input_host}:{cfg.input_port} — {e}"

        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name=f"DetectionServiceThread-{cfg.name}",
        )
        self._thread.start()
        return ""

    # ── RTSP mode ──────────────────────────────────────────────────────────────

    def _do_start_rtsp(self, cfg: ServiceConfig) -> str:
        try:
            from ultralytics import YOLO
            model = YOLO(cfg.model_path)
            self._model_holder["model"] = model
        except Exception as e:
            return f"Failed to load model: {e}"

        import cv2
        # Force RTSP over TCP (same as ffplay -rtsp_transport tcp)
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
        rtsp_url = cfg.rtsp_url

        # Test that the stream opens before returning success
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            cap.release()
            self._model_holder["model"] = None
            return (
                f"Cannot open RTSP stream.\n"
                f"URL: {rtsp_url}\n\n"
                f"Check credentials, IP address, port, and channel path."
            )
        cap.release()

        output_url = (
            f"http://{cfg.output_host}:{cfg.output_port}/result"
            if cfg.output_host else None
        )

        self._stop_event.clear()

        def _loop():
            import cv2 as _cv2
            _cap = _cv2.VideoCapture(rtsp_url, _cv2.CAP_FFMPEG)
            consecutive_fails = 0

            while not self._stop_event.is_set():
                ret, frame = _cap.read()
                if not ret:
                    consecutive_fails += 1
                    log.warning(f"[{cfg.name}] Frame read failed ({consecutive_fails}), reconnecting…")
                    _cap.release()
                    # Wait before reconnect, but respect stop signal
                    if self._stop_event.wait(timeout=3.0):
                        break
                    _cap = _cv2.VideoCapture(rtsp_url, _cv2.CAP_FFMPEG)
                    continue

                consecutive_fails = 0
                m = self._model_holder.get("model")
                if m is None:
                    break

                try:
                    results = m(frame, verbose=False)
                    self._process_rtsp_frame(results, output_url, cfg.name)
                except Exception as e:
                    self._append_log(LogEntry.from_error(str(e)))

                # Wait for next frame interval, exit early if stopped
                self._stop_event.wait(timeout=cfg.rtsp_interval)

            _cap.release()

        self._thread = threading.Thread(target=_loop, daemon=True, name=f"RTSPThread-{cfg.name}")
        self._thread.start()
        return ""

    def _process_rtsp_frame(self, results, output_url: Optional[str], service_name: str):
        if not results:
            return

        result = results[0]
        box = _largest_box(result)
        car_detected = box is not None

        if car_detected:
            area = _bbox_area(box)
            confidence = float(box.conf[0])
            self._area_buffer.append(area)
        else:
            confidence = 0.0
            self._area_buffer.clear()

        direction = (
            _determine_direction(list(self._area_buffer))
            if len(self._area_buffer) >= 2 else "unknown"
        )

        payload = {
            "service_name": service_name,
            "car_detected": car_detected,
            "direction": direction,
            "confidence": round(confidence, 4),
            "frames_analyzed": 1,
            "frames_with_car": 1 if car_detected else 0,
        }

        self._append_log(LogEntry.from_result(payload))

        if output_url:
            try:
                requests.post(output_url, json=payload, timeout=2)
            except Exception:
                pass  # output server not running — silently skip

    # ── Stop ───────────────────────────────────────────────────────────────────

    def stop(self):
        self._stop_event.set()
        if self._server:
            self._server.shutdown()
            self._server = None
        self._model_holder["model"] = None
        self._state = STATE_STOPPED
        self._error_msg = ""
        self._thread = None
        self._area_buffer.clear()


# ── Service registry ───────────────────────────────────────────────────────────

class ServiceRegistry:
    def __init__(self):
        self._configs: list[ServiceConfig] = []
        self._services: dict[str, DetectionService] = {}
        self._lock = threading.Lock()
        self._load_configs()

    def _load_configs(self):
        self._configs = load_saved_configs()

    def _save(self):
        save_configs(self._configs)

    def get_configs(self) -> list[ServiceConfig]:
        with self._lock:
            return list(self._configs)

    def upsert_config(self, cfg: ServiceConfig):
        with self._lock:
            for i, c in enumerate(self._configs):
                if c.name == cfg.name:
                    self._configs[i] = cfg
                    self._save()
                    return
            self._configs.append(cfg)
            self._save()

    def remove_config(self, name: str):
        with self._lock:
            self._configs = [c for c in self._configs if c.name != name]
            self._save()
            svc = self._services.pop(name, None)
        if svc:
            svc.stop()

    def get_config(self, name: str) -> Optional[ServiceConfig]:
        with self._lock:
            for c in self._configs:
                if c.name == name:
                    return c
        return None

    def get_service(self, name: str) -> Optional[DetectionService]:
        with self._lock:
            return self._services.get(name)

    def get_state(self, name: str) -> str:
        svc = self.get_service(name)
        return svc.state if svc else STATE_STOPPED

    def is_running(self, name: str) -> bool:
        return self.get_state(name) == STATE_RUNNING

    def any_running(self) -> bool:
        with self._lock:
            return any(s.is_running for s in self._services.values())

    def start_async(self, name: str, on_done: Callable[[str], None]) -> str:
        cfg = self.get_config(name)
        if cfg is None:
            return f"No config found for '{name}'."

        if not os.path.isfile(cfg.model_path):
            return f"Model file not found:\n{cfg.model_path}"

        # Port check only for HTTP mode
        if not cfg.rtsp_enabled and not is_port_free(cfg.input_host, cfg.input_port):
            return (
                f"Port {cfg.input_port} is already in use.\n"
                f"Choose a different port or stop the process using it."
            )

        with self._lock:
            svc = self._services.get(name)
            if svc and svc.is_running:
                return f"Service '{name}' is already running."
            if svc is None:
                svc = DetectionService()
                self._services[name] = svc

        svc.start_async(cfg, on_done)
        return ""

    def stop(self, name: str):
        with self._lock:
            svc = self._services.get(name)
        if svc:
            svc.stop()

    def restart_async(self, name: str, on_done: Callable[[str], None]) -> str:
        self.stop(name)
        with self._lock:
            self._services.pop(name, None)
        return self.start_async(name, on_done)

    def stop_all(self):
        with self._lock:
            services = list(self._services.values())
            self._services.clear()
        for svc in services:
            svc.stop()

    def auto_start_services(self, on_done: Callable[[str, str], None]):
        for cfg in self.get_configs():
            if cfg.auto_start:
                name = cfg.name
                err = self.start_async(name, lambda e, n=name: on_done(n, e))
                if err:
                    on_done(name, err)


# ── Singleton ──────────────────────────────────────────────────────────────────

_registry = ServiceRegistry()


def get_registry() -> ServiceRegistry:
    return _registry
