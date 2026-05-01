"""Real-time detection service for VisionQ.

Three input modes:
    HTTP  — Runs a Flask HTTP server. Accepts POST /detect with multipart form-data (3-5 images).
    RTSP  — Connects to an IP camera via RTSP, pulls frames continuously.
    VIDEO — Reads frames from a local video file and processes it like a live source.

In both modes YOLO inference is run, direction is determined, and results are pushed
to the configured output URL.  Multiple named service instances can run simultaneously.
"""
from __future__ import annotations

import csv
import io
import json
import os
import queue
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

# ── Direction debug capture ────────────────────────────────────────────────────
# Call start_direction_debug(path) to begin writing a CSV of every frame's
# bbox signals + direction computation.  Call stop_direction_debug() to flush
# and close.  Thread-safe.

_dbg_lock   = threading.Lock()
_dbg_file   = None
_dbg_writer = None

_DBG_COLUMNS = [
    "timestamp", "service", "cls",
    "detected", "cx", "cy", "area", "conf",
    "buf_len",
    "cx_rel", "cy_rel", "area_rel",
    "cx_vote", "cy_vote", "area_vote", "score",
    "raw_dir", "final_dir",
    "gate_threshold", "gate_open",
]


def start_direction_debug(path: str) -> None:
    """Start writing per-frame direction debug data to *path* (CSV)."""
    global _dbg_file, _dbg_writer
    with _dbg_lock:
        if _dbg_file is not None:
            _dbg_file.close()
        _dbg_file = open(path, "w", newline="", encoding="utf-8")
        _dbg_writer = csv.DictWriter(_dbg_file, fieldnames=_DBG_COLUMNS)
        _dbg_writer.writeheader()
        _dbg_file.flush()
    log.info(f"Direction debug logging started → {path}")


def stop_direction_debug() -> None:
    """Flush and close the direction debug CSV."""
    global _dbg_file, _dbg_writer
    with _dbg_lock:
        if _dbg_file is not None:
            _dbg_file.flush()
            _dbg_file.close()
            _dbg_file = None
            _dbg_writer = None
    log.info("Direction debug logging stopped.")


def _dbg_write(row: dict) -> None:
    """Write one row to the debug CSV; no-op when debug is not active."""
    with _dbg_lock:
        if _dbg_writer is not None:
            _dbg_writer.writerow(row)
            _dbg_file.flush()

def _notify_internal(service_name: str, payload: dict) -> None:
    """Fan result out to internal SSE subscribers and the in-memory buffer.

    Safe to call from any background thread — deferred import avoids circular imports.
    """
    try:
        from app.routers.detection import _notify_sse, _result_buffer
        from collections import deque as _deque
        _notify_sse(service_name, payload)
        if service_name not in _result_buffer:
            _result_buffer[service_name] = _deque(maxlen=100)
        _result_buffer[service_name].appendleft(payload)
    except Exception:
        pass  # never break the detection thread over a notification failure


def _notify_mjpeg_frame(service_name: str, frame) -> None:
    """Fan the latest annotated frame out to all MJPEG viewers.

    Safe to call from any background thread — deferred import avoids circular imports.
    """
    try:
        from app.routers.detection import _notify_mjpeg
        _notify_mjpeg(service_name, frame)
    except Exception:
        pass


_PERSIST_PATH = os.path.join(
    os.environ.get("VISIONQ_DATA", os.path.expanduser("~")),
    "config", "visionq_services.json",
)
_MAX_LOG = 50
_MISS_TOLERANCE = 2       # consecutive frames without a car before buffer is cleared
_MIN_DIR_FRAMES = 4       # minimum frames in buffer before direction is considered reliable
_IDLE_HOLD_FRAMES = 5     # consecutive idle readings required before leaving a moving state


def _best_device() -> str:
    """Return 'cuda', 'mps', or 'cpu' depending on what's available."""
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def _save_dataset_frame(frame_np, service_name: str, dataset_dir: str):
    """Save a raw frame (no label) for later annotation.

    Frames are written as <dataset_dir>/<service_name>/<timestamp>.jpg.
    The timestamp makes them chronologically sortable and avoids collisions.
    """
    try:
        import cv2
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        folder = os.path.join(dataset_dir, service_name)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"{ts}.jpg")
        cv2.imwrite(path, frame_np)
    except Exception as e:
        log.warning(f"Failed to save dataset frame: {e}")


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
    # Input source mode: "http" | "rtsp" | "video"
    input_mode: str = "http"
    auto_start: bool = False
    # RTSP source (used when rtsp_enabled=True)
    rtsp_enabled: bool = False
    rtsp_user: str = ""
    rtsp_password: str = ""
    rtsp_ip: str = ""
    rtsp_port: int = 554
    rtsp_channel: str = "Streaming/Channels/102"
    rtsp_interval: float = 0.25  # seconds between frame grabs (0.25 = 4 fps)
    # Video file source (used when input_mode="video")
    video_path: str = ""
    video_loop: bool = True
    conf_threshold: float = 0.5
    strict_output: bool = False        # only emit when direction is known; emit "no_car" when absent
    state_changes_only: bool = False   # only emit when state transitions (forward→idle, idle→no_car, etc.)
    # Dataset capture: save raw frames at a fixed interval for later annotation
    dataset_capture: bool = False
    dataset_interval: int = 10  # save every Nth processed frame (RTSP) or every Nth image (HTTP)
    dataset_dir: str = ""       # folder to write dataset frames
    # Input recording: save raw stream/video frames to a local video file
    record_stream: bool = False
    record_dir: str = ""
    # Gate open trigger: emit gate_open=True when car is idle with bbox area >= this value.
    # Set to 0 to disable.  Typical value: measure the area when the car fills the frame.
    gate_area_threshold: float = 0.0

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
        input_mode = str(d.get("input_mode", "")).strip().lower()
        if input_mode not in {"http", "rtsp", "video"}:
            input_mode = "rtsp" if d.get("rtsp_enabled", False) else "http"

        return ServiceConfig(
            name=d["name"],
            model_path=d["model_path"],
            input_mode=input_mode,
            input_host=d.get("input_host", "0.0.0.0"),
            input_port=d["input_port"],
            output_host=d.get("output_host", "127.0.0.1"),
            output_port=d["output_port"],
            auto_start=d.get("auto_start", False),
            rtsp_enabled=(input_mode == "rtsp"),
            rtsp_user=d.get("rtsp_user", ""),
            rtsp_password=d.get("rtsp_password", ""),
            rtsp_ip=d.get("rtsp_ip", ""),
            rtsp_port=d.get("rtsp_port", 554),
            rtsp_channel=d.get("rtsp_channel", "Streaming/Channels/102"),
            rtsp_interval=d.get("rtsp_interval", 0.5),
            video_path=d.get("video_path", ""),
            video_loop=d.get("video_loop", True),
            conf_threshold=d.get("conf_threshold", 0.5),
            # "report_only_with_direction" is the old key — keep reading it so saved configs still work
            strict_output=d.get("strict_output", d.get("report_only_with_direction", False)),
            state_changes_only=d.get("state_changes_only", False),
            dataset_capture=d.get("dataset_capture", False),
            dataset_interval=d.get("dataset_interval", 10),
            dataset_dir=d.get("dataset_dir", ""),
            record_stream=d.get("record_stream", False),
            record_dir=d.get("record_dir", ""),
            gate_area_threshold=float(d.get("gate_area_threshold", 0.0)),
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


def _bbox_centroid(box) -> tuple[float, float]:
    x1, y1, x2, y2 = box.xyxy[0].tolist()
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def _largest_box(result, class_name: str | None = None):
    if result.boxes is None or len(result.boxes) == 0:
        return None
    boxes = list(result.boxes)
    if class_name is not None:
        target_ids = {cid for cid, n in result.names.items() if n == class_name}
        boxes = [b for b in boxes if int(b.cls[0]) in target_ids]
    if not boxes:
        return None
    return max(boxes, key=lambda b: _bbox_area(b))


def _determine_direction(
    history: list[tuple[float, float, float]],
    use_area: bool = True,
    forward_threshold: int = 1,
    backward_threshold: int = -3,
    signal_threshold: float = 0.005,
    debug_out: Optional[dict] = None,
) -> str:
    """Determine direction from a history of (cx, cy, area) tuples.

    Uses linear regression on three signals independently, then votes:
      - cx  decreasing (moving left)  → forward point
      - cy  increasing (moving down)  → forward point
      - area increasing (getting bigger) → forward point  (only when use_area=True)
    forward_threshold+ signals agree → forward.
    backward_threshold- signals agree → backward.  Otherwise → idle.

    Camera assumption: cars enter upper-right and move diagonally toward
    lower-left when driving forward (approaching the gate).

    Args:
        use_area: When False, the area signal is excluded from voting.
            Use False for car_rear to avoid the "partial-reveal" artefact:
            as a departing car enters the frame from an edge its bbox grows
            (area increases) even though the car is moving away, which creates
            a false forward vote that masks the correct backward signal from
            the centroid.
        forward_threshold: Score at or above which "forward" is returned.
            Defaults to 1 — any single signal agreeing is enough. Handles
            turning cars where centroid movement is curved (near-zero linear
            slope) but area is consistently growing.
        backward_threshold: Score at or below which "backward" is returned.
            Defaults to -3 (all three signals must agree).  Set to -2 when
            use_area=False so that two centroid signals agreeing is sufficient.
    """
    if len(history) < _MIN_DIR_FRAMES:
        return "idle"

    n = len(history)
    t = list(range(n))
    t_mean = (n - 1) / 2.0
    t_den = sum((t[i] - t_mean) ** 2 for i in range(n))
    if t_den == 0:
        return "idle"

    def _slope(vals: list[float]) -> float:
        v_mean = sum(vals) / n
        return sum((t[i] - t_mean) * (vals[i] - v_mean) for i in range(n)) / t_den

    cxs   = [h[0] for h in history]
    cys   = [h[1] for h in history]
    areas = [h[2] for h in history]

    cx_mean   = sum(cxs)   / n
    cy_mean   = sum(cys)   / n
    area_mean = sum(areas) / n

    # Normalize: slope as a fraction of the signal's mean (relative rate of change per frame)
    cx_rel   = _slope(cxs)   / cx_mean   if cx_mean   > 0 else 0.0
    cy_rel   = _slope(cys)   / cy_mean   if cy_mean   > 0 else 0.0
    area_rel = _slope(areas) / area_mean if area_mean > 0 else 0.0

    thr = signal_threshold

    # Score: +1 = forward signal, -1 = backward signal
    score = 0
    cx_vote = cy_vote = area_vote = 0

    if cx_rel < -thr:
        score += 1;  cx_vote = 1
    elif cx_rel > thr:
        score -= 1;  cx_vote = -1

    if cy_rel > thr:
        score += 1;  cy_vote = 1
    elif cy_rel < -thr:
        score -= 1;  cy_vote = -1

    if use_area:
        if area_rel > thr:
            score += 1;  area_vote = 1
        elif area_rel < -thr:
            score -= 1;  area_vote = -1

    if score >= forward_threshold:
        if use_area and area_rel < -thr:
            result = "idle"
        else:
            result = "forward"
    elif score <= backward_threshold:
        result = "backward"
    else:
        result = "idle"

    if debug_out is not None:
        debug_out.update({
            "cx_rel":    round(cx_rel,    6),
            "cy_rel":    round(cy_rel,    6),
            "area_rel":  round(area_rel,  6),
            "cx_vote":   cx_vote,
            "cy_vote":   cy_vote,
            "area_vote": area_vote,
            "score":     score,
            "raw_dir":   result,
        })

    return result


def _invert_direction(direction: str) -> str:
    """Flip forward↔backward for car_rear detections.

    The direction algorithm assumes 'box getting bigger = car approaching = forward'.
    For car_rear this is physically inverted: a growing rear box means the car is
    reversing toward the camera (backward), and a shrinking one means it's driving
    away (forward).
    """
    if direction == "forward":
        return "backward"
    if direction == "backward":
        return "forward"
    return direction  # idle / no_car unchanged


# ── Request log entry ──────────────────────────────────────────────────────────

@dataclass
class LogEntry:
    timestamp: str
    car_detected: bool = False
    car_direction: str = ""
    car_confidence: float = 0.0
    rear_detected: bool = False
    rear_direction: str = ""
    rear_confidence: float = 0.0
    frames: int = 0
    error: str = ""

    @staticmethod
    def from_result(payload: dict) -> "LogEntry":
        car = payload.get("car", {})
        rear = payload.get("car_rear", {})
        return LogEntry(
            timestamp=datetime.now().strftime("%H:%M:%S"),
            car_detected=car.get("detected", False),
            car_direction=car.get("direction", ""),
            car_confidence=car.get("confidence", 0.0),
            rear_detected=rear.get("detected", False),
            rear_direction=rear.get("direction", ""),
            rear_confidence=rear.get("confidence", 0.0),
            frames=payload.get("frames_analyzed", 0),
        )

    @staticmethod
    def from_error(msg: str) -> "LogEntry":
        return LogEntry(
            timestamp=datetime.now().strftime("%H:%M:%S"),
            error=msg,
        )

    def __str__(self) -> str:
        if self.error:
            return f"[{self.timestamp}]  ERROR: {self.error}"
        car_part = (
            f"car={self.car_direction}({self.car_confidence:.2f})"
            if self.car_detected else "car=no_car"
        )
        rear_part = (
            f"rear={self.rear_direction}({self.rear_confidence:.2f})"
            if self.rear_detected else "rear=no_car"
        )
        return f"[{self.timestamp}]  {car_part}  {rear_part}  frames={self.frames}"


# ── Flask app factory (HTTP mode) ──────────────────────────────────────────────

def _make_flask_app(
    service_name: str,
    model_holder: dict,
    output_url: Optional[str],
    log_callback: Callable[[LogEntry], None],
    conf_threshold: float = 0.5,
    strict_output: bool = False,
    state_changes_only: bool = False,
    dataset_capture: bool = False,
    dataset_interval: int = 10,
    dataset_dir: str = "",
):
    from flask import Flask, request, jsonify
    app = Flask(f"detection_service_{service_name}")
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    # Per-class state for state_changes_only mode (persists across HTTP requests)
    _http_state: dict = {"car": "", "car_rear": ""}

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

        # Per-class histories of (cx, cy, area) tuples
        histories:    dict[str, list] = {"car": [], "car_rear": []}
        confidences:  dict[str, list] = {"car": [], "car_rear": []}

        for http_frame_idx, f in enumerate(files):
            try:
                img = Image.open(io.BytesIO(f.read())).convert("RGB")
                img_np = np.array(img)
            except Exception as e:
                log.warning(f"Failed to decode image: {e}")
                continue

            if dataset_capture and dataset_dir and (http_frame_idx % dataset_interval == 0):
                _save_dataset_frame(img_np[:, :, ::-1], service_name, dataset_dir)

            import torch as _torch
            with _torch.no_grad():
                results = model(img_np, conf=conf_threshold, verbose=False)
            if not results:
                continue

            result = results[0]
            for cls_name in ("car", "car_rear"):
                box = _largest_box(result, cls_name)
                if box is not None:
                    cx, cy = _bbox_centroid(box)
                    histories[cls_name].append((cx, cy, _bbox_area(box)))
                    confidences[cls_name].append(float(box.conf[0]))
            del results

        def _resolve(cls_name: str) -> dict:
            hist = histories[cls_name]
            confs = confidences[cls_name]
            detected = bool(hist)
            if not detected:
                current_state = "no_car"
            elif len(hist) >= _MIN_DIR_FRAMES:
                if cls_name == "car_rear":
                    # For car_rear, exclude the area signal to avoid the partial-reveal
                    # artefact (bbox grows as the car enters frame even though it's leaving),
                    # and require only 2 centroid signals to agree (threshold -2 instead of -3).
                    raw = _determine_direction(hist, use_area=False, forward_threshold=2, backward_threshold=-1, signal_threshold=0.005)
                else:
                    raw = _determine_direction(hist)
                current_state = _invert_direction(raw) if cls_name == "car_rear" else raw
            else:
                current_state = None  # still building
            avg_conf = round(sum(confs) / len(confs), 4) if confs else 0.0
            return {
                "detected": detected,
                "direction": current_state if current_state is not None else "idle",
                "confidence": avg_conf,
                "_current_state": current_state,
            }

        car_res  = _resolve("car")
        rear_res = _resolve("car_rear")

        payload = {
            "service_name": service_name,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "car": {
                "detected":   car_res["detected"],
                "direction":  car_res["direction"],
                "confidence": car_res["confidence"],
            },
            "car_rear": {
                "detected":   rear_res["detected"],
                "direction":  rear_res["direction"],
                "confidence": rear_res["confidence"],
            },
            "frames_analyzed": len(files),
        }

        if state_changes_only:
            should_report = False
            for cls_name, res in (("car", car_res), ("car_rear", rear_res)):
                cs = res["_current_state"]
                prev = _http_state[cls_name]
                if cs is None or cs == prev:
                    continue
                # Don't emit "idle" as the very first state after the car appears —
                # wait for a definitive direction so the report is no_car → forward/backward,
                # not no_car → idle → forward/backward.
                if cs == "idle" and prev in ("", "no_car"):
                    continue
                _http_state[cls_name] = cs
                should_report = True
        elif strict_output:
            car_ok  = car_res["detected"]  and car_res["_current_state"]  is not None
            rear_ok = rear_res["detected"] and rear_res["_current_state"] is not None
            no_car  = not car_res["detected"] and not rear_res["detected"]
            should_report = car_ok or rear_ok or no_car
        else:
            should_report = True

        if should_report:
            log_callback(LogEntry.from_result(payload))
            _notify_internal(payload.get("service_name", "unknown"), payload)
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
        # Per-class tracking state for direction (RTSP/video mode)
        self._class_state: dict[str, dict] = self._make_class_state()
        self._gate_last_open: bool = False
        self._last_payload: dict = {}   # last result payload for status polling
        # Live preview — processing thread puts annotated frames here;
        # the Qt main thread polls and renders them (maxsize=1 keeps only latest)
        self._preview_enabled: bool = False
        self._preview_queue: queue.Queue = queue.Queue(maxsize=1)
        # Dataset capture counter (RTSP mode): increments each processed frame
        self._dataset_frame_count: int = 0
        self._on_state_change: Optional[Callable[[], None]] = None
        # RTSP reader thread + active cap reference (kept so stop() can force-release the cap)
        self._reader_thread: Optional[threading.Thread] = None
        self._cap_lock = threading.Lock()
        self._active_cap = None
        # RTSP recording state
        self._video_writer = None
        self._video_lock = threading.Lock()
        self._recording_path: str = ""
        self._record_enabled: bool = False
        self._record_dir_cfg: str = ""
        # Video playback control state (video input mode only)
        self._video_state_lock = threading.Lock()
        self._video_speed: float = 1.0
        self._video_seek_target_ms: float = -1.0  # -1 = no pending seek
        self._video_pos_ms: float = 0.0
        self._video_duration_ms: float = 0.0
        self._video_paused: bool = False
        self._video_step: bool = False  # step one frame while paused

    @staticmethod
    def _make_class_state() -> dict:
        return {
            cls: {"buffer": deque(maxlen=8), "misses": 0, "last_state": "", "idle_streak": 0}
            for cls in ("car", "car_rear")
        }

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
        self._class_state = self._make_class_state()
        self._gate_last_open = False
        self._dataset_frame_count = 0
        mode = (cfg.input_mode or ("rtsp" if cfg.rtsp_enabled else "http")).lower()
        self._record_enabled = bool(cfg.record_stream and mode in ("rtsp", "video"))
        self._record_dir_cfg = cfg.record_dir
        self._close_video_writer()

        def _worker():
            error = self._do_start(cfg)
            if error:
                self._state = STATE_ERROR
                self._error_msg = error
                self._append_log(LogEntry.from_error(error))
            else:
                self._state = STATE_RUNNING
            on_done(error)

        t = threading.Thread(target=_worker, daemon=True, name=f"StartWorker-{cfg.name}")
        t.start()

    def _do_start(self, cfg: ServiceConfig) -> str:
        mode = (cfg.input_mode or ("rtsp" if cfg.rtsp_enabled else "http")).lower()
        if mode == "rtsp":
            return self._do_start_rtsp(cfg)
        if mode == "video":
            return self._do_start_video(cfg)
        return self._do_start_http(cfg)

    # ── HTTP mode ──────────────────────────────────────────────────────────────

    def _do_start_http(self, cfg: ServiceConfig) -> str:
        try:
            from ultralytics import YOLO
            device = _best_device()
            model = YOLO(cfg.model_path)
            model.to(device)
            log.info(f"[{cfg.name}] Model loaded on {device.upper()}")
            self._model_holder["model"] = model
        except Exception as e:
            return f"Failed to load model: {e}"

        output_url = (
            f"http://{cfg.output_host}:{cfg.output_port}/result"
            if cfg.output_host.strip() else None
        )
        app = _make_flask_app(
            cfg.name, self._model_holder, output_url, self._append_log,
            conf_threshold=cfg.conf_threshold,
            strict_output=cfg.strict_output,
            state_changes_only=cfg.state_changes_only,
            dataset_capture=cfg.dataset_capture,
            dataset_interval=cfg.dataset_interval,
            dataset_dir=cfg.dataset_dir,
        )

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
            device = _best_device()
            model = YOLO(cfg.model_path)
            model.to(device)
            log.info(f"[{cfg.name}] Model loaded on {device.upper()}")
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

        # Shared latest frame between reader and processing threads
        latest: dict = {"frame": None, "ok": False}
        latest_lock = threading.Lock()

        def _reader():
            """Continuously reads frames as fast as the stream delivers them.
            Only the most recent frame is kept — old frames are discarded,
            which prevents the processing thread from working on stale data."""
            import cv2 as _cv2
            _cap = _cv2.VideoCapture(rtsp_url, _cv2.CAP_FFMPEG)
            _cap.set(_cv2.CAP_PROP_BUFFERSIZE, 1)
            with self._cap_lock:
                self._active_cap = _cap
            consecutive_fails = 0

            while not self._stop_event.is_set():
                try:
                    ret, frame = _cap.read()
                except Exception:
                    # cap was force-released by stop() while read() was blocking
                    break
                if not ret:
                    consecutive_fails += 1
                    log.warning(f"[{cfg.name}] Frame read failed ({consecutive_fails}), reconnecting…")
                    _cap.release()
                    with latest_lock:
                        latest["ok"] = False
                    if self._stop_event.wait(timeout=3.0):
                        break
                    _cap = _cv2.VideoCapture(rtsp_url, _cv2.CAP_FFMPEG)
                    _cap.set(_cv2.CAP_PROP_BUFFERSIZE, 1)
                    with self._cap_lock:
                        self._active_cap = _cap
                    continue

                consecutive_fails = 0
                with latest_lock:
                    latest["frame"] = frame
                    latest["ok"] = True

            _cap.release()
            with self._cap_lock:
                self._active_cap = None

        def _loop():
            """Processes the latest available frame at the configured interval."""
            import torch
            _frame_count_local = 0

            while not self._stop_event.is_set():
                self._stop_event.wait(timeout=cfg.rtsp_interval)

                with latest_lock:
                    ok = latest["ok"]
                    frame = latest["frame"]

                if not ok or frame is None:
                    continue

                m = self._model_holder.get("model")
                if m is None:
                    break

                try:
                    with torch.no_grad():
                        results = m(frame, conf=cfg.conf_threshold, verbose=False)
                    self._dataset_frame_count += 1
                    frame_summary = self._process_rtsp_frame(
                        results, frame, output_url, cfg.name,
                        cfg.strict_output,
                        cfg.state_changes_only,
                        cfg.dataset_capture, cfg.dataset_interval,
                        cfg.dataset_dir, self._dataset_frame_count,
                        cfg.gate_area_threshold,
                    )
                    if frame_summary:
                        self._last_payload = frame_summary
                    if self._record_enabled:
                        self._record_input_frame(
                            service_name=cfg.name,
                            frame=frame,
                            record_dir=self._record_dir_cfg,
                        )
                    if self._preview_enabled and results:
                        _frame = results[0].plot()
                        try:
                            self._preview_queue.put_nowait(_frame)
                        except queue.Full:
                            pass
                        _notify_mjpeg_frame(cfg.name, _frame)
                except Exception as e:
                    self._append_log(LogEntry.from_error(str(e)))
                finally:
                    # Explicitly release result tensors — YOLO results hold GPU memory
                    # and Python's GC won't always collect them promptly in a tight loop
                    try:
                        del results
                    except NameError:
                        pass
                    _frame_count_local += 1
                    # Periodically flush the CUDA cache to prevent silent accumulation
                    if _frame_count_local % 500 == 0 and torch.cuda.is_available():
                        torch.cuda.empty_cache()

        self._reader_thread = threading.Thread(target=_reader, daemon=True, name=f"RTSPReader-{cfg.name}")
        self._reader_thread.start()

        self._thread = threading.Thread(target=_loop, daemon=True, name=f"RTSPThread-{cfg.name}")
        self._thread.start()
        return ""

    def _do_start_video(self, cfg: ServiceConfig) -> str:
        try:
            from ultralytics import YOLO
            device = _best_device()
            model = YOLO(cfg.model_path)
            model.to(device)
            log.info(f"[{cfg.name}] Model loaded on {device.upper()}")
            self._model_holder["model"] = model
        except Exception as e:
            return f"Failed to load model: {e}"

        import cv2

        video_path = cfg.video_path.strip()
        if not video_path:
            self._model_holder["model"] = None
            return "Video file path is required for video input mode."

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            cap.release()
            self._model_holder["model"] = None
            return (
                f"Cannot open video file.\n"
                f"Path: {video_path}\n\n"
                f"Check file path, permissions, and codec support."
            )
        cap.release()

        output_url = (
            f"http://{cfg.output_host}:{cfg.output_port}/result"
            if cfg.output_host else None
        )

        self._stop_event.clear()

        # Shared latest frame between reader and processing threads
        latest: dict = {"frame": None, "ok": False}
        latest_lock = threading.Lock()

        def _reader():
            """Read video frames and loop to the beginning at EOF (demo mode)."""
            import cv2 as _cv2

            _cap = _cv2.VideoCapture(video_path)
            with self._cap_lock:
                self._active_cap = _cap

            # Determine total duration for the progress slider
            _fps = _cap.get(_cv2.CAP_PROP_FPS) or 25.0
            _frame_count = _cap.get(_cv2.CAP_PROP_FRAME_COUNT)
            with self._video_state_lock:
                self._video_duration_ms = (_frame_count / _fps * 1000.0) if _frame_count > 0 else 0.0
                self._video_speed = 1.0
                self._video_seek_target_ms = -1.0
                self._video_pos_ms = 0.0
                self._video_paused = False
                self._video_step = False

            loop_count = 0
            while not self._stop_event.is_set():
                # Read shared state atomically
                with self._video_state_lock:
                    seek_target = self._video_seek_target_ms
                    speed = self._video_speed
                    paused = self._video_paused
                    step = self._video_step
                    if step:
                        self._video_step = False  # consume the step request

                # While paused and no step/seek pending: idle and poll for changes
                if paused and not step and seek_target < 0:
                    self._stop_event.wait(timeout=0.05)
                    continue

                # Apply any pending seek before reading the next frame
                if seek_target >= 0:
                    _cap.set(_cv2.CAP_PROP_POS_MSEC, seek_target)
                    with self._video_state_lock:
                        self._video_seek_target_ms = -1.0
                        self._video_pos_ms = seek_target

                try:
                    ret, frame = _cap.read()
                except Exception:
                    # cap was force-released by stop() while read() was blocking
                    break
                if not ret:
                    if cfg.video_loop:
                        loop_count += 1
                        _cap.set(_cv2.CAP_PROP_POS_FRAMES, 0)
                        with self._video_state_lock:
                            self._video_pos_ms = 0.0
                        try:
                            ret, frame = _cap.read()
                        except Exception:
                            break
                        if not ret:
                            _cap.release()
                            if self._stop_event.wait(timeout=1.0):
                                break
                            _cap = _cv2.VideoCapture(video_path)
                            with self._cap_lock:
                                self._active_cap = _cap
                            continue

                        if loop_count <= 3 or loop_count % 10 == 0:
                            self._append_log(LogEntry.from_error(
                                f"Video reached end, looping to start (x{loop_count})."
                            ))
                    else:
                        self._append_log(LogEntry.from_error("Video ended. Stopping service."))
                        self._stop_event.set()
                        break
                else:
                    # Update current position so the UI slider can track progress
                    pos_ms = _cap.get(_cv2.CAP_PROP_POS_MSEC)
                    with self._video_state_lock:
                        self._video_pos_ms = pos_ms

                with latest_lock:
                    latest["frame"] = frame
                    latest["ok"] = True

                # When paused we just delivered a single step frame — go back to idle.
                # When playing, pace the reader to match the processing interval / speed.
                if not paused:
                    interval = cfg.rtsp_interval / max(0.1, speed)
                    self._stop_event.wait(timeout=interval)

            _cap.release()
            with self._cap_lock:
                self._active_cap = None

        def _loop():
            """Processes the latest available frame at the configured interval."""
            import torch
            _frame_count_local = 0

            while not self._stop_event.is_set():
                self._stop_event.wait(timeout=cfg.rtsp_interval)

                with latest_lock:
                    ok = latest["ok"]
                    frame = latest["frame"]

                if not ok or frame is None:
                    continue

                m = self._model_holder.get("model")
                if m is None:
                    break

                try:
                    with torch.no_grad():
                        results = m(frame, conf=cfg.conf_threshold, verbose=False)
                    self._dataset_frame_count += 1
                    _vs = self._process_rtsp_frame(
                        results, frame, output_url, cfg.name,
                        cfg.strict_output,
                        cfg.state_changes_only,
                        cfg.dataset_capture, cfg.dataset_interval,
                        cfg.dataset_dir, self._dataset_frame_count,
                        cfg.gate_area_threshold,
                    )
                    if _vs:
                        self._last_payload = _vs
                    if self._record_enabled:
                        self._record_input_frame(
                            service_name=cfg.name,
                            frame=frame,
                            record_dir=self._record_dir_cfg,
                        )
                    if self._preview_enabled and results:
                        _frame = results[0].plot()
                        try:
                            self._preview_queue.put_nowait(_frame)
                        except queue.Full:
                            pass
                        _notify_mjpeg_frame(cfg.name, _frame)
                except Exception as e:
                    self._append_log(LogEntry.from_error(str(e)))
                finally:
                    try:
                        del results
                    except NameError:
                        pass
                    _frame_count_local += 1
                    if _frame_count_local % 500 == 0 and torch.cuda.is_available():
                        torch.cuda.empty_cache()

        self._reader_thread = threading.Thread(target=_reader, daemon=True, name=f"VideoReader-{cfg.name}")
        self._reader_thread.start()

        self._thread = threading.Thread(target=_loop, daemon=True, name=f"VideoThread-{cfg.name}")
        self._thread.start()
        return ""

    def _resolve_record_dir(self, configured_dir: str) -> str:
        if configured_dir.strip():
            return configured_dir.strip()
        return "/villapro-data/recordings"

    def _open_video_writer_if_needed(
        self,
        service_name: str,
        frame_shape: tuple[int, int, int],
        record_dir: str,
    ) -> None:
        with self._video_lock:
            if self._video_writer is not None:
                return

            import cv2

            h, w = frame_shape[:2]
            interval = self._config.rtsp_interval if self._config else 0.25
            fps = max(1.0, round(1.0 / interval, 3))
            out_dir = os.path.join(self._resolve_record_dir(record_dir), service_name)
            os.makedirs(out_dir, exist_ok=True)

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = os.path.join(out_dir, f"{service_name}_{ts}.mp4")

            # mp4v is broadly available on Windows OpenCV builds.
            writer = cv2.VideoWriter(
                out_path,
                cv2.VideoWriter_fourcc(*"mp4v"),
                fps,
                (w, h),
            )

            if not writer.isOpened():
                writer.release()
                raise RuntimeError(f"Failed to open video writer: {out_path}")

            self._video_writer = writer
            self._recording_path = out_path
            self._append_log(
                LogEntry.from_error(f"Recording started: {out_path}")
            )

    def _close_video_writer(self) -> None:
        with self._video_lock:
            if self._video_writer is None:
                return
            try:
                self._video_writer.release()
            except Exception:
                pass
            finally:
                if self._recording_path:
                    self._append_log(
                        LogEntry.from_error(f"Recording saved: {self._recording_path}")
                    )
                self._video_writer = None
                self._recording_path = ""

    def _record_input_frame(
        self,
        service_name: str,
        frame,
        record_dir: str,
    ) -> None:
        # Intentionally save raw (unannotated) input frames for reproducible model demos.
        raw_frame = frame.copy()
        self._open_video_writer_if_needed(
            service_name=service_name,
            frame_shape=raw_frame.shape,
            record_dir=record_dir,
        )
        with self._video_lock:
            if self._video_writer is not None:
                self._video_writer.write(raw_frame)

    def can_record(self) -> bool:
        cfg = self._config
        if cfg is None:
            return False
        mode = (cfg.input_mode or ("rtsp" if cfg.rtsp_enabled else "http")).lower()
        return mode in ("rtsp", "video")

    @property
    def is_recording(self) -> bool:
        return self._record_enabled

    def start_recording(self, record_dir: Optional[str] = None) -> str:
        if self._state != STATE_RUNNING:
            return "Service must be running before recording can start."
        if not self.can_record():
            return "Recording is available only for RTSP/video input services."
        if self._record_enabled:
            return ""

        if record_dir is not None:
            self._record_dir_cfg = record_dir

        self._record_enabled = True
        self._append_log(LogEntry.from_error("Recording enabled (raw stream)."))
        return ""

    def stop_recording(self):
        if not self._record_enabled and self._video_writer is None:
            return
        self._record_enabled = False
        self._close_video_writer()

    # ── Direction debug helpers ────────────────────────────────────────────────

    @property
    def is_direction_debugging(self) -> bool:
        with _dbg_lock:
            return _dbg_file is not None

    def start_direction_debug(self, path: str) -> None:
        """Start writing per-frame direction signals to a CSV at *path*."""
        self._dbg_path = path
        start_direction_debug(path)

    def stop_direction_debug(self) -> str:
        """Flush and close the direction debug CSV. Returns the file path."""
        stop_direction_debug()
        return getattr(self, "_dbg_path", "")

    @property
    def is_previewing(self) -> bool:
        return self._preview_enabled

    def start_preview(self) -> str:
        if self._state != STATE_RUNNING:
            return "Service must be running before preview can start."
        if not self.can_record():  # same modes: rtsp / video
            return "Preview is available only for RTSP/video input services."
        # Drain stale frames before enabling
        while not self._preview_queue.empty():
            try:
                self._preview_queue.get_nowait()
            except queue.Empty:
                break
        self._preview_enabled = True
        return ""

    def stop_preview(self):
        self._preview_enabled = False
        # Drain the queue so the Qt poll timer stops seeing frames immediately
        while not self._preview_queue.empty():
            try:
                self._preview_queue.get_nowait()
            except queue.Empty:
                break

    def get_preview_frame(self):
        """Return the latest annotated frame (numpy BGR) or None. Called from Qt main thread."""
        try:
            return self._preview_queue.get_nowait()
        except queue.Empty:
            return None

    def get_preview_frame_blocking(self, timeout: float = 0.1):
        """Block up to *timeout* seconds for the next annotated frame, or return None."""
        try:
            return self._preview_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    # ── Dataset capture toggle ─────────────────────────────────────────────────

    @property
    def is_dataset_capturing(self) -> bool:
        cfg = self._config
        return cfg is not None and cfg.dataset_capture

    def start_dataset_capture(self, dataset_dir: str = "", interval: int = 10) -> str:
        if self._state != STATE_RUNNING:
            return "Service must be running before dataset capture can start."
        cfg = self._config
        if cfg is None:
            return "No config."
        if dataset_dir:
            cfg.dataset_dir = dataset_dir
        cfg.dataset_interval = interval
        cfg.dataset_capture = True
        return ""

    def stop_dataset_capture(self):
        cfg = self._config
        if cfg is not None:
            cfg.dataset_capture = False

    # ── Video playback controls ────────────────────────────────────────────────

    def set_video_speed(self, speed: float):
        """Set playback speed multiplier (0.5, 1.0, 2.0, 4.0). Thread-safe."""
        with self._video_state_lock:
            self._video_speed = max(0.1, float(speed))

    def seek_video_relative(self, delta_ms: float):
        """Seek by delta_ms milliseconds relative to current position. Thread-safe."""
        with self._video_state_lock:
            target = self._video_pos_ms + delta_ms
            target = max(0.0, target)
            if self._video_duration_ms > 0:
                target = min(target, self._video_duration_ms - 500.0)
            self._video_seek_target_ms = target

    def seek_video_to_ms(self, target_ms: float):
        """Seek to an absolute position in milliseconds. Thread-safe."""
        with self._video_state_lock:
            target_ms = max(0.0, float(target_ms))
            if self._video_duration_ms > 0:
                target_ms = min(target_ms, self._video_duration_ms - 500.0)
            self._video_seek_target_ms = target_ms

    def toggle_video_pause(self) -> bool:
        """Toggle pause/play. Returns new paused state."""
        with self._video_state_lock:
            self._video_paused = not self._video_paused
            return self._video_paused

    def step_video_frame(self):
        """While paused, advance exactly one frame. Has no effect when playing."""
        with self._video_state_lock:
            self._video_step = True

    def get_video_state(self) -> tuple:
        """Return (pos_ms, duration_ms, speed, paused). Safe to call from Qt main thread."""
        with self._video_state_lock:
            return self._video_pos_ms, self._video_duration_ms, self._video_speed, self._video_paused

    def _process_rtsp_frame(
        self, results, frame, output_url: Optional[str], service_name: str,
        strict_output: bool = False,
        state_changes_only: bool = False,
        dataset_capture: bool = False,
        dataset_interval: int = 10,
        dataset_dir: str = "",
        frame_count: int = 0,
        gate_area_threshold: float = 0.0,
    ) -> dict:
        if not results:
            return {}

        result = results[0]

        if dataset_capture and dataset_dir and frame_count % dataset_interval == 0:
            _save_dataset_frame(frame, service_name, dataset_dir)

        # Process each class independently
        class_results: dict[str, dict] = {}
        for cls_name in ("car", "car_rear"):
            state = self._class_state[cls_name]
            buf   = state["buffer"]

            box      = _largest_box(result, cls_name)
            detected = box is not None

            if detected:
                state["misses"] = 0
                cx, cy = _bbox_centroid(box)
                confidence = float(box.conf[0])
                buf.append((cx, cy, _bbox_area(box)))
            else:
                confidence = 0.0
                state["misses"] += 1
                if state["misses"] >= _MISS_TOLERANCE:
                    buf.clear()

            buf_list = list(buf)
            if not detected:
                current_state = "no_car"
                state["idle_streak"] = 0
                _dbg_write({
                    "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                    "service": service_name, "cls": cls_name,
                    "detected": False, "cx": "", "cy": "", "area": "", "conf": "",
                    "buf_len": 0, "cx_rel": "", "cy_rel": "", "area_rel": "",
                    "cx_vote": "", "cy_vote": "", "area_vote": "", "score": "",
                    "raw_dir": "no_car", "final_dir": "no_car",
                    "gate_threshold": gate_area_threshold if cls_name == "car" else "",
                    "gate_open": False if cls_name == "car" else "",
                })
            elif len(buf_list) >= _MIN_DIR_FRAMES:
                dbg: dict = {}
                if cls_name == "car_rear":
                    raw = _determine_direction(
                        buf_list, use_area=False, forward_threshold=2,
                        backward_threshold=-1, signal_threshold=0.005,
                        debug_out=dbg,
                    )
                else:
                    raw = _determine_direction(buf_list, debug_out=dbg)
                # car_rear direction signals are physically inverted vs car
                resolved = _invert_direction(raw) if cls_name == "car_rear" else raw

                # Hysteresis: don't flip back to idle on a brief slowdown.
                # Only switch away from a moving state after _IDLE_HOLD_FRAMES
                # consecutive idle readings.
                if resolved == "idle" and state["last_state"] in ("forward", "backward"):
                    state["idle_streak"] += 1
                    if state["idle_streak"] < _IDLE_HOLD_FRAMES:
                        resolved = state["last_state"]  # hold previous direction
                else:
                    state["idle_streak"] = 0

                current_state = resolved
                last_entry = buf_list[-1]
                _gate_now = bool(
                    cls_name == "car"
                    and gate_area_threshold > 0
                    and resolved == "idle"
                    and last_entry[2] >= gate_area_threshold
                )
                _dbg_write({
                    "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                    "service": service_name, "cls": cls_name,
                    "detected": True,
                    "cx":   round(last_entry[0], 1),
                    "cy":   round(last_entry[1], 1),
                    "area": round(last_entry[2], 1),
                    "conf": round(confidence, 3),
                    "buf_len": len(buf_list),
                    **dbg,
                    "final_dir": resolved,
                    "gate_threshold": gate_area_threshold if cls_name == "car" else "",
                    "gate_open": _gate_now if cls_name == "car" else "",
                })
            else:
                current_state = None  # still building
                last_entry = buf_list[-1] if buf_list else (0, 0, 0)
                _dbg_write({
                    "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                    "service": service_name, "cls": cls_name,
                    "detected": True,
                    "cx":   round(last_entry[0], 1),
                    "cy":   round(last_entry[1], 1),
                    "area": round(last_entry[2], 1),
                    "conf": round(confidence, 3),
                    "buf_len": len(buf_list),
                    "cx_rel": "", "cy_rel": "", "area_rel": "",
                    "cx_vote": "", "cy_vote": "", "area_vote": "", "score": "",
                    "raw_dir": "building", "final_dir": "building",
                    "gate_threshold": gate_area_threshold if cls_name == "car" else "",
                    "gate_open": False if cls_name == "car" else "",
                })

            class_results[cls_name] = {
                "detected":       detected,
                "direction":      current_state if current_state is not None else "idle",
                "confidence":     round(confidence, 4),
                "_current_state": current_state,
                "_misses":        state["misses"],
                "_area":          _bbox_area(box) if detected else 0.0,
            }

        # ── Gate open detection ───────────────────────────────────────────────
        # Gate opens for incoming cars only (class "car", not "car_rear").
        # Conditions: car detected, direction confirmed as idle (not still building),
        # and the bounding box area exceeds the configured threshold (= car is close).
        car_res = class_results["car"]
        # Gate logic — simple: open when car is idle at the gate (area >= threshold).
        gate_open = bool(
            gate_area_threshold > 0
            and car_res["detected"]
            and car_res["_current_state"] is not None
            and car_res["direction"] == "idle"
            and car_res["_area"] >= gate_area_threshold
        )

        payload = {
            "service_name": service_name,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "car": {
                "detected":   car_res["detected"],
                "direction":  car_res["direction"],
                "confidence": car_res["confidence"],
            },
            "car_rear": {
                "detected":   class_results["car_rear"]["detected"],
                "direction":  class_results["car_rear"]["direction"],
                "confidence": class_results["car_rear"]["confidence"],
            },
            "gate": {"open": gate_open},
            "frames_analyzed": 1,
        }

        if state_changes_only:
            should_report = False
            for cls_name in ("car", "car_rear"):
                cs = class_results[cls_name]["_current_state"]
                prev = self._class_state[cls_name]["last_state"]
                if cs is None or cs == prev:
                    continue
                # Don't emit "idle" as the very first state after the car appears —
                # wait for a definitive direction so the report is no_car → forward/backward,
                # not no_car → idle → forward/backward.
                if cs == "idle" and prev in ("", "no_car"):
                    continue
                self._class_state[cls_name]["last_state"] = cs
                should_report = True
            # Gate: report only on the closed→open transition, then reset when car leaves.
            if gate_open and not self._gate_last_open:
                self._gate_last_open = True
                should_report = True
            elif not gate_open:
                self._gate_last_open = False
        elif strict_output:
            car_ok  = (class_results["car"]["detected"]
                       and class_results["car"]["_current_state"] is not None)
            rear_ok = (class_results["car_rear"]["detected"]
                       and class_results["car_rear"]["_current_state"] is not None)
            car_just_gone  = (not class_results["car"]["detected"]
                              and class_results["car"]["_misses"] == _MISS_TOLERANCE)
            rear_just_gone = (not class_results["car_rear"]["detected"]
                              and class_results["car_rear"]["_misses"] == _MISS_TOLERANCE)
            should_report = car_ok or rear_ok or car_just_gone or rear_just_gone
        else:
            should_report = True

        if should_report:
            self._append_log(LogEntry.from_result(payload))
            _notify_internal(service_name, payload)
            if output_url:
                threading.Thread(
                    target=self._push_result,
                    args=(output_url, payload),
                    daemon=True,
                ).start()

        return payload

    @staticmethod
    def _push_result(url: str, payload: dict):
        try:
            requests.post(url, json=payload, timeout=2)
        except Exception:
            pass  # output server not running — silently skip

    # ── Stop ───────────────────────────────────────────────────────────────────

    def stop(self):
        self._stop_event.set()

        # Force-release the RTSP cap immediately so the blocking _cap.read() call
        # in the reader thread returns right away instead of waiting for a timeout.
        with self._cap_lock:
            if self._active_cap is not None:
                try:
                    self._active_cap.release()
                except Exception:
                    pass
                self._active_cap = None

        # Shut down HTTP server (if running in HTTP mode)
        if self._server:
            self._server.shutdown()
            self._server = None

        # Wait for threads to actually finish (2s timeout each)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=2.0)

        # Drop model reference then flush GPU memory so VRAM is released immediately
        self._model_holder["model"] = None
        self._record_enabled = False
        self._close_video_writer()
        self.stop_preview()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

        self._state = STATE_STOPPED
        self._error_msg = ""
        self._thread = None
        self._reader_thread = None
        self._class_state = self._make_class_state()
        self._gate_last_open = False
        self._dataset_frame_count = 0


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

        mode = (cfg.input_mode or ("rtsp" if cfg.rtsp_enabled else "http")).lower()

        # Port check only for HTTP mode
        if mode == "http" and not is_port_free(cfg.input_host, cfg.input_port):
            return (
                f"Port {cfg.input_port} is already in use.\n"
                f"Choose a different port or stop the process using it."
            )

        if mode == "video" and not os.path.isfile(cfg.video_path):
            return f"Video file not found:\n{cfg.video_path}"

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
