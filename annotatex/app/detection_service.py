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
import threading
import logging
from dataclasses import dataclass, asdict
from typing import Optional

import numpy as np
import requests
from flask import Flask, request, jsonify
from PIL import Image

log = logging.getLogger("detection_service")

_PERSIST_PATH = os.path.expanduser("~/.visionq_services.json")


# ── Config dataclass ────────────────────────────────────────────────────────────

@dataclass
class ServiceConfig:
    name: str
    model_path: str
    input_host: str
    input_port: int
    output_host: str
    output_port: int

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


# ── Flask app factory ──────────────────────────────────────────────────────────

def _make_flask_app(service_name: str, model_holder: dict, output_url: Optional[str]) -> Flask:
    app = Flask(f"detection_service_{service_name}")
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    @app.route("/detect", methods=["POST"])
    def detect():
        model = model_holder.get("model")
        if model is None:
            return jsonify({"error": "Model not loaded"}), 503

        files = request.files.getlist("images")
        if not files:
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

class DetectionService:
    """Manages a single running Flask detection server."""

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._server = None
        self._model_holder: dict = {"model": None}
        self._running = False
        self._config: Optional[ServiceConfig] = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def config(self) -> Optional[ServiceConfig]:
        return self._config

    def start(self, cfg: ServiceConfig) -> str:
        """Start the service. Returns empty string on success, error message on failure."""
        if self._running:
            return "Service is already running."

        try:
            from ultralytics import YOLO
            model = YOLO(cfg.model_path)
            self._model_holder["model"] = model
        except Exception as e:
            return f"Failed to load model: {e}"

        output_url = f"http://{cfg.output_host}:{cfg.output_port}/result"
        app = _make_flask_app(cfg.name, self._model_holder, output_url)

        from werkzeug.serving import make_server
        try:
            self._server = make_server(cfg.input_host, cfg.input_port, app)
        except Exception as e:
            self._model_holder["model"] = None
            return f"Failed to bind to {cfg.input_host}:{cfg.input_port} — {e}"

        self._config = cfg
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name=f"DetectionServiceThread-{cfg.name}",
        )
        self._thread.start()
        self._running = True
        return ""

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server = None
        self._model_holder["model"] = None
        self._running = False
        self._thread = None


# ── Service registry ───────────────────────────────────────────────────────────

class ServiceRegistry:
    """
    Manages multiple named DetectionService instances plus persistent configs.

    Configs are saved to ~/.visionq_services.json.
    A config can exist without a running instance (stopped state).
    """

    def __init__(self):
        self._configs: list[ServiceConfig] = []       # all known configs (ordered)
        self._running: dict[str, DetectionService] = {}  # name → running instance
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
        """Add or update a config by name. Does not start/stop the service."""
        with self._lock:
            for i, c in enumerate(self._configs):
                if c.name == cfg.name:
                    self._configs[i] = cfg
                    self._save()
                    return
            self._configs.append(cfg)
            self._save()

    def remove_config(self, name: str):
        """Remove config and stop service if running."""
        with self._lock:
            self._configs = [c for c in self._configs if c.name != name]
            self._save()
            svc = self._running.pop(name, None)
        if svc:
            svc.stop()

    def get_config(self, name: str) -> Optional[ServiceConfig]:
        with self._lock:
            for c in self._configs:
                if c.name == name:
                    return c
        return None

    # ── Runtime management ─────────────────────────────────────────────────────

    def is_running(self, name: str) -> bool:
        with self._lock:
            svc = self._running.get(name)
            return svc is not None and svc.is_running

    def any_running(self) -> bool:
        with self._lock:
            return any(s.is_running for s in self._running.values())

    def start(self, name: str) -> str:
        """Start the service for the given config name. Returns error or ''."""
        cfg = self.get_config(name)
        if cfg is None:
            return f"No config found for '{name}'."
        with self._lock:
            if name in self._running and self._running[name].is_running:
                return f"Service '{name}' is already running."
            svc = DetectionService()
            self._running[name] = svc
        return svc.start(cfg)

    def stop(self, name: str):
        with self._lock:
            svc = self._running.pop(name, None)
        if svc:
            svc.stop()

    def restart(self, name: str) -> str:
        """Stop if running, then start again."""
        self.stop(name)
        return self.start(name)

    def stop_all(self):
        with self._lock:
            services = list(self._running.values())
            self._running.clear()
        for svc in services:
            svc.stop()


# ── Singleton ──────────────────────────────────────────────────────────────────

_registry = ServiceRegistry()


def get_registry() -> ServiceRegistry:
    return _registry
