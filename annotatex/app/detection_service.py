"""Real-time detection service for VisionQ.

Runs a Flask HTTP server in a background thread.
Accepts POST /detect with multipart form-data (3-5 images).
Runs YOLO inference, determines car direction, pushes result to output IP.
Multiple named service instances can run simultaneously on different ports.
"""
from __future__ import annotations

import io
import json
import os
import socket
import threading
import logging
from collections import deque
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Optional, Callable

import numpy as np
import requests
from flask import Flask, request, jsonify
from PIL import Image

log = logging.getLogger("detection_service")

_PERSIST_PATH = os.path.expanduser("~/.visionq_services.json")

# Max request log entries kept per service
_MAX_LOG = 50


# ── Config dataclass ────────────────────────────────────────────────────────────

@dataclass
class ServiceConfig:
    name: str
    model_path: str
    input_host: str
    input_port: int
    output_host: str
    output_port: int
    auto_start: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

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
    """Return True if the port is available to bind."""
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


# ── Flask app factory ──────────────────────────────────────────────────────────

def _make_flask_app(
    service_name: str,
    model_holder: dict,
    output_url: Optional[str],
    log_callback: Callable[[LogEntry], None],
) -> Flask:
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
            except Exception as e:
                log.warning(f"Failed to push to output: {e}")

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

# States for the loading lifecycle
STATE_STOPPED  = "stopped"
STATE_LOADING  = "loading"   # model loading in background
STATE_RUNNING  = "running"
STATE_ERROR    = "error"


class DetectionService:
    """Manages a single running Flask detection server."""

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._server = None
        self._model_holder: dict = {"model": None}
        self._config: Optional[ServiceConfig] = None
        self._state: str = STATE_STOPPED
        self._error_msg: str = ""
        self._request_log: deque[LogEntry] = deque(maxlen=_MAX_LOG)
        self._log_lock = threading.Lock()
        # Called on UI thread via polling — just append to deque, UI polls
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
        """
        Start loading the model and binding the server in a background thread.
        on_done(error_str) is called when finished — empty string = success.
        The UI should poll self.state to show a spinner while STATE_LOADING.
        """
        if self._state == STATE_RUNNING:
            on_done("Service is already running.")
            return
        if self._state == STATE_LOADING:
            on_done("Service is already loading.")
            return

        self._state = STATE_LOADING
        self._error_msg = ""
        self._config = cfg

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
        """Blocking start — runs in background thread. Returns error or ''."""
        try:
            from ultralytics import YOLO
            model = YOLO(cfg.model_path)
            self._model_holder["model"] = model
        except Exception as e:
            return f"Failed to load model: {e}"

        output_url = f"http://{cfg.output_host}:{cfg.output_port}/result"
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

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server = None
        self._model_holder["model"] = None
        self._state = STATE_STOPPED
        self._error_msg = ""
        self._thread = None


# ── Service registry ───────────────────────────────────────────────────────────

class ServiceRegistry:
    """
    Manages multiple named DetectionService instances plus persistent configs.
    Configs saved to ~/.visionq_services.json.
    """

    def __init__(self):
        self._configs: list[ServiceConfig] = []
        self._services: dict[str, DetectionService] = {}
        self._lock = threading.Lock()
        self._load_configs()

    # ── Config management ──────────────────────────────────────────────────────

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

    # ── Runtime management ─────────────────────────────────────────────────────

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
        """
        Validate then kick off async start. Returns immediate error string if
        validation fails, otherwise '' and on_done will be called when done.
        """
        cfg = self.get_config(name)
        if cfg is None:
            return f"No config found for '{name}'."

        # Validate model file exists
        if not os.path.isfile(cfg.model_path):
            return f"Model file not found:\n{cfg.model_path}"

        # Check port availability
        if not is_port_free(cfg.input_host, cfg.input_port):
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
        # Remove old service instance so a fresh one is created
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
        """Start all services marked auto_start. on_done(name, error) called per service."""
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
