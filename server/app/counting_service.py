"""Parking occupancy counting service for VisionQ.

Subscribes to a detection service's output and maintains a count of cars
currently in the parking lot by tracking class/direction transitions:

  car  forward  → no_car  :  car entered   → count + 1
  car_rear forward → no_car :  car exited    → count - 1
  car  backward → no_car  :  reversed away  → no change
  car_rear backward → no_car : reversed back in → no change

Emits a JSON message on each meaningful transition and on reset/status events.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime

import requests
from typing import Optional, Callable

log = logging.getLogger("counting_service")

_PERSIST_PATH = os.path.join(
    os.environ.get("VISIONQ_DATA", os.path.expanduser("~")),
    "config", "visionq_counters.json",
)

STATE_STOPPED = "stopped"
STATE_RUNNING = "running"
STATE_ERROR   = "error"

# Directions that indicate a committed pass (not a reversal / ambiguous stop)
_COUNTING_DIRECTIONS = ("forward", "backward")
# If the incoming bbox area is below this fraction of the last-seen area, treat it as a
# different car (the old one left and a new, smaller one appeared in the same frame).
_AREA_JUMP_RATIO = 0.25


def _notify_counting_internal(service_name: str, payload: dict) -> None:
    """Fan a counting result out to SSE subscribers and the in-memory buffer.

    Safe to call from any thread — uses the same deferred-import pattern as
    detection_service._notify_internal to avoid circular imports.
    """
    try:
        from app.routers.counting import _notify_counting_sse, _counting_result_buffer
        from collections import deque as _deque
        _notify_counting_sse(service_name, payload)
        if service_name not in _counting_result_buffer:
            _counting_result_buffer[service_name] = _deque(maxlen=100)
        _counting_result_buffer[service_name].appendleft(payload)
    except Exception:
        pass


# ── Config ────────────────────────────────────────────────────────────────────

@dataclass
class CountingConfig:
    name: str
    source_service: str  # name of the DetectionService to subscribe to
    auto_start: bool = False
    tcp_push_enabled: bool = False
    tcp_push_host: str = "0.0.0.0"
    tcp_push_port: int = 0
    tcp_push_certfile: str = ""
    tcp_push_keyfile: str = ""
    tcp_push_ca_certs: str = ""
    initial_count: int = 0
    output_host: str = ""
    output_port: int = 0
    # How long (ms) a class must be continuously absent before the count fires.
    # Prevents double-counts from brief detection gaps (occlusion, lighting, etc.).
    no_car_grace_ms: int = 1500

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "CountingConfig":
        return CountingConfig(
            name=d["name"],
            source_service=d["source_service"],
            auto_start=d.get("auto_start", False),
            tcp_push_enabled=d.get("tcp_push_enabled", False),
            tcp_push_host=d.get("tcp_push_host", "0.0.0.0"),
            tcp_push_port=int(d.get("tcp_push_port", 0)),
            tcp_push_certfile=d.get("tcp_push_certfile", ""),
            tcp_push_keyfile=d.get("tcp_push_keyfile", ""),
            tcp_push_ca_certs=d.get("tcp_push_ca_certs", ""),
            initial_count=int(d.get("initial_count", 0)),
            output_host=d.get("output_host", ""),
            output_port=int(d.get("output_port", 0)),
            no_car_grace_ms=int(d.get("no_car_grace_ms", 1500)),
        )


def load_saved_counter_configs() -> list[CountingConfig]:
    try:
        with open(_PERSIST_PATH, "r") as f:
            data = json.load(f)
        return [CountingConfig.from_dict(d) for d in data]
    except Exception:
        return []


def save_counter_configs(configs: list[CountingConfig]):
    try:
        os.makedirs(os.path.dirname(_PERSIST_PATH), exist_ok=True)
        with open(_PERSIST_PATH, "w") as f:
            json.dump([c.to_dict() for c in configs], f, indent=2)
    except Exception as e:
        log.warning(f"Failed to save counter configs: {e}")


# ── Service ───────────────────────────────────────────────────────────────────

class CountingService:
    """Subscribes to a detection service and tracks parking occupancy."""

    def __init__(self):
        self._config: Optional[CountingConfig] = None
        self._state: str = STATE_STOPPED
        self._error_msg: str = ""
        self._count: int = 0
        self._last_reset_dt: datetime = datetime.now()
        # Lock protecting _cls_state and _count — needed because _fire_count runs
        # on a threading.Timer thread, not the asyncio callback thread.
        self._state_lock = threading.Lock()
        # Per-class state:
        #   detected  — was the class present in the last payload?
        #   last_dir  — last confirmed direction while the car was visible
        #   timer     — pending threading.Timer (None = car present / already counted)
        #   counted   — True once the count has been fired for this absence
        self._cls_state: dict[str, dict] = {
            cls: {"detected": False, "last_dir": "", "timer": None, "counted": False, "last_area": 0.0}
            for cls in ("car", "car_rear")
        }
        # Per-track-ID state used when the source detection service has tracking enabled.
        # Keys are (cls_name, track_id).  Each entry has the same shape as _cls_state values
        # but without last_area (tracking gives us hard ID boundaries — no area heuristic needed).
        self._track_id_state: dict[tuple[str, int], dict] = {}

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def state(self) -> str:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state == STATE_RUNNING

    @property
    def error_msg(self) -> str:
        return self._error_msg

    @property
    def config(self) -> Optional[CountingConfig]:
        return self._config

    def get_counts(self) -> dict:
        return {
            "count": self._count,
            "last_reset": self._last_reset_dt.isoformat(),
        }

    # ── HTTP output push ───────────────────────────────────────────────────────

    @staticmethod
    def _push_result(url: str, payload: dict):
        try:
            requests.post(url, json=payload, timeout=2)
        except Exception:
            pass

    # ── Payload helpers ────────────────────────────────────────────────────────

    def _make_payload(self, event: str, trigger_class: str = "",
                      direction: str = "", change: int = 0) -> dict:
        return {
            "service_name": self._config.name,
            "source_service": self._config.source_service,
            "timestamp": datetime.now().isoformat(),
            "event": event,
            "trigger_class": trigger_class,
            "direction": direction,
            "change": change,
            "count": self._count,
            "last_reset": self._last_reset_dt.isoformat(),
        }

    # ── Detection result hook ──────────────────────────────────────────────────

    def _on_detection_result(self, payload: dict) -> None:
        """Called on the asyncio event loop when a detection result arrives.

        When the source service has tracking enabled, payload["track_events"] is a
        list of per-car-ID events and each car gets its own independent grace timer.
        When tracking is disabled, falls back to the legacy per-class logic.
        """
        grace_s = (self._config.no_car_grace_ms / 1000.0) if self._config else 1.5

        track_events = payload.get("track_events")
        if track_events is not None:
            # ── Tracking mode ────────────────────────────────────────────────
            # Each car ID has completely independent state; two cars can be in
            # the frame simultaneously without interfering with each other.
            for event in track_events:
                cls_name  = event.get("cls", "")
                track_id  = event.get("id", -1)
                detected  = event.get("detected", False)
                direction = event.get("direction", "no_car")

                if cls_name not in ("car", "car_rear"):
                    continue

                key = (cls_name, track_id)
                with self._state_lock:
                    if key not in self._track_id_state:
                        self._track_id_state[key] = {
                            "detected": False, "last_dir": "",
                            "timer": None, "counted": False,
                        }
                    st = self._track_id_state[key]

                    if detected:
                        t = st["timer"]
                        if t:
                            t.cancel()
                            st["timer"] = None
                            st["counted"] = False
                        st["detected"] = True
                        if direction in _COUNTING_DIRECTIONS:
                            st["last_dir"] = direction

                    else:
                        # Car departed. This event is only generated when the ID was
                        # present in the previous frame and is now absent — always real.
                        # Use the direction from the event itself: the detection service's
                        # per-ID buffer sees every frame, even ones state_changes_only
                        # suppressed, so its direction is always up-to-date.
                        t = st["timer"]
                        if t:
                            t.cancel()
                        last_dir = direction if direction in _COUNTING_DIRECTIONS else st["last_dir"]
                        if last_dir:
                            st["counted"] = False
                            new_t = threading.Timer(
                                0, self._fire_count_tracked, args=(key, last_dir)
                            )
                            new_t.daemon = True
                            new_t.start()
                            st["timer"] = new_t
                        st["detected"] = False
            return

        # ── Legacy mode (no tracking) ─────────────────────────────────────────
        for cls_name in ("car", "car_rear"):
            cls_data  = payload.get(cls_name, {})
            detected  = cls_data.get("detected", False)
            direction = cls_data.get("direction", "no_car")

            with self._state_lock:
                st = self._cls_state[cls_name]

                if detected:
                    new_area = cls_data.get("area", 0.0)
                    t = st["timer"]
                    if t:
                        prev_area = st["last_area"]
                        same_car = (
                            prev_area <= 0
                            or new_area <= 0
                            or new_area >= _AREA_JUMP_RATIO * prev_area
                        )
                        if same_car:
                            t.cancel()
                            st["timer"] = None
                            st["counted"] = False
                            if new_area > 0:
                                st["last_area"] = new_area
                    else:
                        st["counted"] = False
                        if new_area > 0:
                            st["last_area"] = new_area
                    st["detected"] = True
                    if direction in _COUNTING_DIRECTIONS:
                        st["last_dir"] = direction

                elif st["detected"]:
                    t = st["timer"]
                    if t:
                        t.cancel()
                    last_dir = st["last_dir"]
                    st["counted"] = False
                    new_t = threading.Timer(
                        grace_s, self._fire_count, args=(cls_name, last_dir)
                    )
                    new_t.daemon = True
                    new_t.start()
                    st["timer"] = new_t
                    st["detected"] = False

    def _fire_count(self, cls_name: str, last_dir: str) -> None:
        """Called by threading.Timer after the grace period expires."""
        out = None
        with self._state_lock:
            st = self._cls_state[cls_name]
            if st["counted"]:
                return  # car reappeared and cancelled, or already fired
            st["counted"] = True
            st["timer"] = None
            change = self._compute_change(cls_name, last_dir)
            st["last_dir"] = ""
            if change == 0 or self._config is None:
                return
            self._count += change
            out = self._make_payload(
                event="car_passed",
                trigger_class=cls_name,
                direction=last_dir,
                change=change,
            )

        _notify_counting_internal(self._config.name, out)
        if self._config.output_host.strip():
            url = f"http://{self._config.output_host}:{self._config.output_port}/result"
            threading.Thread(target=self._push_result, args=(url, out), daemon=True).start()

    def _fire_count_tracked(self, key: tuple[str, int], last_dir: str) -> None:
        """Grace-period callback for a per-track-ID departure (tracking mode)."""
        out = None
        cls_name = key[0]
        with self._state_lock:
            st = self._track_id_state.get(key)
            if st is None or st["counted"]:
                return
            st["counted"] = True
            st["timer"] = None
            change = self._compute_change(cls_name, last_dir)
            self._track_id_state.pop(key, None)  # clean up finished track
            if change == 0 or self._config is None:
                return
            self._count += change
            out = self._make_payload(
                event="car_passed",
                trigger_class=cls_name,
                direction=last_dir,
                change=change,
            )

        _notify_counting_internal(self._config.name, out)
        if self._config.output_host.strip():
            url = f"http://{self._config.output_host}:{self._config.output_port}/result"
            threading.Thread(target=self._push_result, args=(url, out), daemon=True).start()

    @staticmethod
    def _compute_change(cls_name: str, last_direction: str) -> int:
        """Map (class, last direction before no_car) → occupancy delta."""
        if last_direction == "forward":
            # car forward = entering; car_rear forward = exiting
            return +1 if cls_name == "car" else -1
        if last_direction == "backward":
            # car backward = reversed away (no entry); car_rear backward = reversed back in (no exit)
            return 0
        return 0  # idle or unknown — don't count

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self, cfg: CountingConfig) -> str:
        if self._state == STATE_RUNNING:
            return "Counter is already running."
        self._config = cfg
        self._count = cfg.initial_count
        self._cls_state = {
            cls: {"detected": False, "last_dir": "", "timer": None, "counted": False, "last_area": 0.0}
            for cls in ("car", "car_rear")
        }
        self._track_id_state = {}
        try:
            from app.routers.detection import register_counting_hook
            register_counting_hook(cfg.source_service, self._on_detection_result)
        except Exception as e:
            self._state = STATE_ERROR
            self._error_msg = str(e)
            return str(e)
        # Enable per-object tracking on the source detection service so we get
        # per-ID departure events instead of relying on area heuristics.
        try:
            from app.detection_service import get_registry as _det_reg
            _svc = _det_reg().get_service(cfg.source_service)
            if _svc is not None:
                _svc.enable_tracking()
        except Exception:
            pass
        self._state = STATE_RUNNING
        self._error_msg = ""
        # Announce current state so SSE subscribers get an immediate snapshot
        status_payload = self._make_payload("status")
        _notify_counting_internal(cfg.name, status_payload)
        return ""

    def _cancel_all_timers(self):
        with self._state_lock:
            for st in self._cls_state.values():
                t = st["timer"]
                if t:
                    t.cancel()
                    st["timer"] = None
            for st in self._track_id_state.values():
                t = st["timer"]
                if t:
                    t.cancel()
                    st["timer"] = None

    def stop(self):
        self._cancel_all_timers()
        if self._config:
            try:
                from app.routers.detection import unregister_counting_hook
                unregister_counting_hook(self._config.source_service, self._on_detection_result)
            except Exception:
                pass
            try:
                from app.detection_service import get_registry as _det_reg
                _svc = _det_reg().get_service(self._config.source_service)
                if _svc is not None:
                    _svc.disable_tracking()
            except Exception:
                pass
        self._track_id_state = {}
        self._state = STATE_STOPPED
        self._error_msg = ""

    def reset_counts(self):
        self._cancel_all_timers()
        with self._state_lock:
            self._count = 0
            self._last_reset_dt = datetime.now()
            self._cls_state = {
                cls: {"detected": False, "last_dir": "", "timer": None, "counted": False, "last_area": 0.0}
                for cls in ("car", "car_rear")
            }
            self._track_id_state = {}
        if self._config:
            reset_payload = self._make_payload("reset")
            _notify_counting_internal(self._config.name, reset_payload)


# ── Registry ──────────────────────────────────────────────────────────────────

class CountingServiceRegistry:
    def __init__(self):
        self._configs: list[CountingConfig] = []
        self._services: dict[str, CountingService] = {}
        self._lock = threading.Lock()
        self._load_configs()

    def _load_configs(self):
        self._configs = load_saved_counter_configs()

    def _save(self):
        save_counter_configs(self._configs)

    def get_configs(self) -> list[CountingConfig]:
        with self._lock:
            return list(self._configs)

    def get_config(self, name: str) -> Optional[CountingConfig]:
        with self._lock:
            for c in self._configs:
                if c.name == name:
                    return c
        return None

    def upsert_config(self, cfg: CountingConfig):
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

    def get_service(self, name: str) -> Optional[CountingService]:
        with self._lock:
            return self._services.get(name)

    def get_state(self, name: str) -> str:
        svc = self.get_service(name)
        return svc.state if svc else STATE_STOPPED

    def start(self, name: str) -> str:
        cfg = self.get_config(name)
        if cfg is None:
            return f"No config found for '{name}'."
        with self._lock:
            svc = self._services.get(name)
            if svc is None:
                svc = CountingService()
                self._services[name] = svc
        err = svc.start(cfg)
        if not err and cfg.tcp_push_enabled and cfg.tcp_push_port > 0:
            from app.tcp_push import get_tcp_registry
            tcp_err = get_tcp_registry().start(
                service_name=name,
                host=cfg.tcp_push_host,
                port=cfg.tcp_push_port,
                certfile=cfg.tcp_push_certfile or None,
                keyfile=cfg.tcp_push_keyfile or None,
                ca_certs=cfg.tcp_push_ca_certs or None,
            )
            if tcp_err:
                log.warning(f"[{name}] TCP push start failed: {tcp_err}")
        return err

    def stop(self, name: str):
        svc = self.get_service(name)
        if svc:
            svc.stop()
        from app.tcp_push import get_tcp_registry
        get_tcp_registry().stop(name)

    def stop_all(self):
        with self._lock:
            names = list(self._services.keys())
        for name in names:
            self.stop(name)

    def auto_start_services(self, on_done: Callable[[str, str], None]):
        for cfg in self.get_configs():
            if cfg.auto_start:
                err = self.start(cfg.name)
                on_done(cfg.name, err)


_registry: Optional[CountingServiceRegistry] = None
_registry_lock = threading.Lock()


def get_counting_registry() -> CountingServiceRegistry:
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = CountingServiceRegistry()
    return _registry
