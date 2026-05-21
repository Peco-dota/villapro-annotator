"""Detection services API — manage YOLO inference services, SSE stream, TCP push."""
import asyncio
import json
import logging
import os
import threading
from typing import Optional, AsyncGenerator

log = logging.getLogger("detection")

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.auth import require_user
from app.detection_service import (
    get_registry, ServiceConfig,
    STATE_STOPPED, STATE_LOADING, STATE_RUNNING, STATE_ERROR,
)
from app.tcp_push import get_tcp_registry

router = APIRouter(prefix="/api/detection", tags=["detection"])

# SSE subscribers: service_name -> list of asyncio queues
_sse_queues: dict[str, list[asyncio.Queue]] = {}
_sse_lock = asyncio.Lock()
_event_loop: asyncio.AbstractEventLoop | None = None

# MJPEG subscribers: service_name -> list of per-viewer asyncio queues (numpy BGR frames)
_mjpeg_queues: dict[str, list[asyncio.Queue]] = {}

# Counting hooks: detection service name → list of callbacks registered by counting services.
# Called from _do_notify (asyncio event loop thread). register/unregister may be called
# from FastAPI sync route handlers (threadpool), so access is protected by a lock.
_counting_hooks: dict[str, list] = {}
_counting_hooks_lock = threading.Lock()


def register_counting_hook(source_service: str, callback) -> None:
    with _counting_hooks_lock:
        _counting_hooks.setdefault(source_service, []).append(callback)


def unregister_counting_hook(source_service: str, callback) -> None:
    with _counting_hooks_lock:
        hooks = _counting_hooks.get(source_service, [])
        try:
            hooks.remove(callback)
        except ValueError:
            pass


def _notify_mjpeg(service_name: str, frame) -> None:
    """Called from detection threads to fan-out a frame to all MJPEG viewers."""
    if _event_loop is None:
        return
    _event_loop.call_soon_threadsafe(_do_notify_mjpeg, service_name, frame)


def _do_notify_mjpeg(service_name: str, frame) -> None:
    for q in list(_mjpeg_queues.get(service_name, [])):
        try:
            q.put_nowait(frame)
        except asyncio.QueueFull:
            pass  # slow viewer — drop this frame rather than build lag


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Called from the app lifespan to give background threads a reference to the event loop."""
    global _event_loop
    _event_loop = loop


def _notify_sse(service_name: str, payload: dict):
    """Called from detection service threads to fan-out to SSE subscribers."""
    if _event_loop is None or _event_loop.is_closed():
        return
    _event_loop.call_soon_threadsafe(_do_notify, service_name, payload)


def _do_notify(service_name: str, payload: dict):
    queues = _sse_queues.get(service_name, [])
    for q in list(queues):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass
    # Push to TCP clients
    get_tcp_registry().push(service_name, payload)
    # Forward to any counting services subscribed to this detection service
    with _counting_hooks_lock:
        hooks = list(_counting_hooks.get(service_name, []))
    for cb in hooks:
        try:
            cb(payload)
        except Exception:
            pass


# ── Config CRUD ───────────────────────────────────────────────────────────────

class ServiceConfigIn(BaseModel):
    name: str
    model_path: str
    input_mode: str = "http"
    input_host: str = "0.0.0.0"
    input_port: int = 5000
    output_host: str = "127.0.0.1"
    output_port: int = 6060
    auto_start: bool = False
    rtsp_user: str = ""
    rtsp_password: str = ""
    rtsp_ip: str = ""
    rtsp_port: int = 554
    rtsp_channel: str = "Streaming/Channels/102"
    rtsp_low_latency: bool = False
    rtsp_interval: float = 0.25
    video_path: str = ""
    video_loop: bool = True
    conf_threshold: float = 0.5
    strict_output: bool = False
    state_changes_only: bool = False
    dataset_capture: bool = False
    dataset_interval: int = 10
    dataset_dir: str = ""
    record_stream: bool = False
    record_dir: str = ""
    gate_trigger_mode: str = "off"
    gate_area_threshold: float = 0.0
    gate_line: list[float] = []
    gate_line_side: list[float] = []
    # TCP push settings
    tcp_push_enabled: bool = False
    tcp_push_host: str = "0.0.0.0"
    tcp_push_port: int = 0
    tcp_push_certfile: str = ""
    tcp_push_keyfile: str = ""
    tcp_push_ca_certs: str = ""
    kind: str = "detection"
    enhance_gamma: float = 1.0
    enhance_clahe: bool = False
    enhance_clahe_clip: float = 2.0


def _cfg_to_dict(cfg: ServiceConfig, registry) -> dict:
    d = cfg.to_dict()
    d["state"] = registry.get_state(cfg.name)
    svc = registry.get_service(cfg.name)
    d["log"] = [str(e) for e in (svc.get_log_entries() if svc else [])]
    tcp_reg = get_tcp_registry()
    d["tcp_push_running"] = tcp_reg.is_running(cfg.name)
    return d


@router.get("/services")
def list_services(_user: dict = Depends(require_user)):
    reg = get_registry()
    return [_cfg_to_dict(c, reg) for c in reg.get_configs()]


@router.get("/services/{name}")
def get_service(name: str, _user: dict = Depends(require_user)):
    reg = get_registry()
    cfg = reg.get_config(name)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Service '{name}' not found.")
    return _cfg_to_dict(cfg, reg)


@router.post("/services", status_code=201)
def create_or_update_service(req: ServiceConfigIn, _user: dict = Depends(require_user)):
    cfg = ServiceConfig(
        name=req.name,
        model_path=req.model_path,
        input_mode=req.input_mode,
        input_host=req.input_host,
        input_port=req.input_port,
        output_host=req.output_host,
        output_port=req.output_port,
        auto_start=req.auto_start,
        rtsp_enabled=(req.input_mode == "rtsp"),
        rtsp_user=req.rtsp_user,
        rtsp_password=req.rtsp_password,
        rtsp_ip=req.rtsp_ip,
        rtsp_port=req.rtsp_port,
        rtsp_channel=req.rtsp_channel,
        rtsp_low_latency=req.rtsp_low_latency,
        rtsp_interval=req.rtsp_interval,
        video_path=req.video_path,
        video_loop=req.video_loop,
        conf_threshold=req.conf_threshold,
        strict_output=req.strict_output,
        state_changes_only=req.state_changes_only,
        dataset_capture=req.dataset_capture,
        dataset_interval=req.dataset_interval,
        dataset_dir=req.dataset_dir,
        record_stream=req.record_stream,
        record_dir=req.record_dir,
        gate_trigger_mode=req.gate_trigger_mode,
        gate_area_threshold=req.gate_area_threshold,
        gate_line=list(req.gate_line),
        gate_line_side=list(req.gate_line_side),
        tcp_push_enabled=req.tcp_push_enabled,
        tcp_push_host=req.tcp_push_host,
        tcp_push_port=req.tcp_push_port,
        tcp_push_certfile=req.tcp_push_certfile,
        tcp_push_keyfile=req.tcp_push_keyfile,
        tcp_push_ca_certs=req.tcp_push_ca_certs,
        kind=req.kind,
        enhance_gamma=req.enhance_gamma,
        enhance_clahe=req.enhance_clahe,
        enhance_clahe_clip=req.enhance_clahe_clip,
    )
    get_registry().upsert_config(cfg)
    return _cfg_to_dict(cfg, get_registry())


class DuplicateRequest(BaseModel):
    new_name: str


@router.post("/services/{name}/duplicate", status_code=201)
def duplicate_service(name: str, req: DuplicateRequest, _user: dict = Depends(require_user)):
    reg = get_registry()
    cfg = reg.get_config(name)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Service '{name}' not found.")
    if reg.get_config(req.new_name) is not None:
        raise HTTPException(status_code=409, detail=f"Service '{req.new_name}' already exists.")
    import copy
    new_cfg = copy.deepcopy(cfg)
    new_cfg.name = req.new_name
    reg.upsert_config(new_cfg)
    return _cfg_to_dict(new_cfg, reg)


@router.delete("/services/{name}")
def delete_service(name: str, _user: dict = Depends(require_user)):
    reg = get_registry()
    if reg.get_config(name) is None:
        raise HTTPException(status_code=404, detail=f"Service '{name}' not found.")
    get_tcp_registry().stop(name)
    reg.remove_config(name)
    return {"deleted": name}


# ── Start / stop ──────────────────────────────────────────────────────────────

@router.post("/services/{name}/start")
def start_service(name: str, _user: dict = Depends(require_user)):
    reg = get_registry()
    # Clear stale results from the previous run so the receiver shows a fresh feed
    _result_buffer.pop(name, None)

    def _on_done(error: str):
        pass  # SSE subscribers will see state change on next poll

    err = reg.start_async(name, _on_done)
    if err:
        raise HTTPException(status_code=400, detail=err)
    return {"started": name, "state": reg.get_state(name)}


@router.post("/services/{name}/stop")
def stop_service(name: str, _user: dict = Depends(require_user)):
    reg = get_registry()
    if reg.get_config(name) is None:
        raise HTTPException(status_code=404, detail=f"Service '{name}' not found.")
    reg.stop(name)
    return {"stopped": name, "state": reg.get_state(name)}


@router.post("/services/{name}/restart")
def restart_service(name: str, _user: dict = Depends(require_user)):
    reg = get_registry()

    def _on_done(error: str):
        pass

    err = reg.restart_async(name, _on_done)
    if err:
        raise HTTPException(status_code=400, detail=err)
    return {"restarted": name, "state": reg.get_state(name)}


# ── Service status & log ──────────────────────────────────────────────────────

@router.get("/services/{name}/status")
def get_service_status(name: str, _user: dict = Depends(require_user)):
    reg = get_registry()
    cfg = reg.get_config(name)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Service '{name}' not found.")
    svc = reg.get_service(name)
    return {
        "name": name,
        "state": reg.get_state(name),
        "running": reg.get_state(name) == STATE_RUNNING,
        "error": svc.error_msg if svc else "",
        "is_recording": svc.is_recording if svc else False,
        "is_previewing": svc.is_previewing if svc else False,
        "is_direction_debugging": svc.is_direction_debugging if svc else False,
        "is_dataset_capturing": svc.is_dataset_capturing if svc else False,
        "tcp_push_running": get_tcp_registry().is_running(name),
        "last_payload": svc._last_payload if svc else {},
    }


@router.get("/services/{name}/result")
def get_service_result(name: str, _user: dict = Depends(require_user)):
    """Return the last detection result for this service (same payload as SSE/TCP push)."""
    reg = get_registry()
    if reg.get_config(name) is None:
        raise HTTPException(status_code=404, detail=f"Service '{name}' not found.")
    svc = reg.get_service(name)
    if svc is None or not svc._last_payload:
        return {"service_name": name, "available": False}
    return svc._last_payload


@router.get("/services/{name}/log")
def get_service_log(name: str, _user: dict = Depends(require_user)):
    reg = get_registry()
    svc = reg.get_service(name)
    if svc is None:
        return {"name": name, "log": []}
    return {"name": name, "log": [str(e) for e in svc.get_log_entries()]}


# ── Recording ─────────────────────────────────────────────────────────────────

@router.post("/services/{name}/recording/start")
def start_recording(name: str, record_dir: Optional[str] = None,
                    _user: dict = Depends(require_user)):
    svc = get_registry().get_service(name)
    if svc is None:
        raise HTTPException(status_code=404, detail="Service not running.")
    err = svc.start_recording(record_dir)
    if err:
        raise HTTPException(status_code=400, detail=err)
    return {"recording": True}


@router.post("/services/{name}/recording/stop")
def stop_recording(name: str, _user: dict = Depends(require_user)):
    svc = get_registry().get_service(name)
    if svc is None:
        raise HTTPException(status_code=404, detail="Service not running.")
    svc.stop_recording()
    return {"recording": False}


# ── Direction debug ───────────────────────────────────────────────────────────

@router.post("/services/{name}/debug/start")
def start_debug(name: str, path: Optional[str] = None,
                _user: dict = Depends(require_user)):
    svc = get_registry().get_service(name)
    if svc is None:
        raise HTTPException(status_code=404, detail=f"Service '{name}' not found in registry. Make sure it is running.")
    if not path:
        from datetime import datetime
        data_root = os.environ.get("VISIONQ_DATA", "/data")
        debug_dir = os.path.join(data_root, "debug", name)
        try:
            os.makedirs(debug_dir, exist_ok=True)
        except OSError as e:
            log.error("debug start: cannot create dir %s: %s", debug_dir, e)
            raise HTTPException(status_code=500, detail=f"Cannot create debug directory {debug_dir}: {e}")
        path = os.path.join(debug_dir, f"debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
    try:
        svc.start_direction_debug(path)
    except OSError as e:
        log.error("debug start: cannot open file %s: %s", path, e)
        raise HTTPException(status_code=500, detail=f"Cannot create debug file {path}: {e}")
    log.info("Debug started for service '%s' → %s", name, path)
    return {"debug_path": path}


@router.post("/services/{name}/debug/stop")
def stop_debug(name: str, _user: dict = Depends(require_user)):
    svc = get_registry().get_service(name)
    if svc is None:
        raise HTTPException(status_code=404, detail=f"Service '{name}' not found in registry.")
    path = svc.stop_direction_debug()
    if not path:
        raise HTTPException(status_code=400, detail="Debug was not active for this service.")
    if not os.path.isfile(path):
        log.warning("Debug stopped for '%s' but file not found: %s", name, path)
        raise HTTPException(status_code=500, detail=f"Debug file was not written: {path}")
    log.info("Debug stopped for service '%s' → %s", name, path)
    return {"debug_path": path}


# ── Video controls ────────────────────────────────────────────────────────────

@router.post("/services/{name}/video/pause")
def toggle_pause(name: str, _user: dict = Depends(require_user)):
    svc = get_registry().get_service(name)
    if svc is None:
        raise HTTPException(status_code=404, detail="Service not running.")
    paused = svc.toggle_video_pause()
    return {"paused": paused}


@router.post("/services/{name}/video/speed")
def set_speed(name: str, speed: float, _user: dict = Depends(require_user)):
    svc = get_registry().get_service(name)
    if svc is None:
        raise HTTPException(status_code=404, detail="Service not running.")
    svc.set_video_speed(speed)
    return {"speed": speed}


@router.post("/services/{name}/video/seek")
def seek_video(name: str, ms: Optional[float] = None,
               delta: Optional[float] = None, _user: dict = Depends(require_user)):
    svc = get_registry().get_service(name)
    if svc is None:
        raise HTTPException(status_code=404, detail="Service not running.")
    if ms is not None:
        svc.seek_video_to_ms(ms)
    elif delta is not None:
        svc.seek_video_relative(delta)
    else:
        raise HTTPException(status_code=400, detail="Provide ms or delta.")
    return {"ok": True}


@router.post("/services/{name}/video/step")
def step_frame(name: str, _user: dict = Depends(require_user)):
    svc = get_registry().get_service(name)
    if svc is None:
        raise HTTPException(status_code=404, detail="Service not running.")
    svc.step_video_frame()
    return {"ok": True}


@router.post("/services/{name}/video/reverse")
def toggle_reverse(name: str, _user: dict = Depends(require_user)):
    svc = get_registry().get_service(name)
    if svc is None:
        raise HTTPException(status_code=404, detail="Service not running.")
    reverse = svc.toggle_video_reverse()
    return {"reverse": reverse}


@router.get("/services/{name}/video/state")
def get_video_state(name: str, _user: dict = Depends(require_user)):
    svc = get_registry().get_service(name)
    if svc is None:
        raise HTTPException(status_code=404, detail="Service not running.")
    pos_ms, duration_ms, speed, paused, reverse = svc.get_video_state()
    return {"pos_ms": pos_ms, "duration_ms": duration_ms, "speed": speed, "paused": paused, "reverse": reverse}


# ── Preview frame (JPEG snapshot) ────────────────────────────────────────────

@router.post("/services/{name}/preview/start")
def start_preview(name: str, _user: dict = Depends(require_user)):
    svc = get_registry().get_service(name)
    if svc is None:
        raise HTTPException(status_code=404, detail="Service not running.")
    err = svc.start_preview()
    if err:
        raise HTTPException(status_code=400, detail=err)
    return {"preview": True}


@router.post("/services/{name}/preview/stop")
def stop_preview(name: str, _user: dict = Depends(require_user)):
    svc = get_registry().get_service(name)
    if svc is None:
        raise HTTPException(status_code=404, detail="Service not running.")
    svc.stop_preview()
    return {"preview": False}


@router.get("/services/{name}/preview/frame")
def get_preview_frame(name: str, token: Optional[str] = None, _user: dict = Depends(require_user)):
    """Return latest annotated frame as a JPEG image."""
    svc = get_registry().get_service(name)
    if svc is None:
        raise HTTPException(status_code=404, detail="Service not running.")
    frame = svc.get_preview_frame()
    if frame is None:
        raise HTTPException(status_code=204, detail="No frame available.")
    import cv2
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to encode frame.")
    return Response(content=bytes(buf), media_type="image/jpeg")


@router.get("/services/{name}/preview/mjpeg")
async def mjpeg_stream(request: Request, name: str, token: Optional[str] = None,
                       _user: dict = Depends(require_user)):
    """Stream annotated frames as MJPEG.

    Each connected viewer gets its own queue so multiple tabs/clients all
    receive every frame independently without competing for the same data.
    """
    svc = get_registry().get_service(name)
    if svc is None:
        raise HTTPException(status_code=404, detail="Service not running.")

    import cv2

    q: asyncio.Queue = asyncio.Queue(maxsize=2)
    _mjpeg_queues.setdefault(name, []).append(q)

    async def generate():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    frame = await asyncio.wait_for(q.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                if ok:
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n" + bytes(buf) + b"\r\n"
                    )
        finally:
            try:
                _mjpeg_queues[name].remove(q)
            except (ValueError, KeyError):
                pass

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")


# ── Dataset capture ───────────────────────────────────────────────────────────

@router.post("/services/{name}/dataset/start")
def start_dataset(name: str, dataset_dir: Optional[str] = None,
                  interval: Optional[int] = None, _user: dict = Depends(require_user)):
    svc = get_registry().get_service(name)
    cfg = get_registry().get_config(name)
    if svc is None or cfg is None:
        raise HTTPException(status_code=404, detail="Service not running.")
    svc.start_dataset_capture(
        dataset_dir or cfg.dataset_dir or os.path.join(os.environ.get("VISIONQ_DATA", "/data"), "datasets"),
        interval or cfg.dataset_interval or 10,
    )
    return {"dataset_capture": True}


@router.post("/services/{name}/dataset/stop")
def stop_dataset(name: str, _user: dict = Depends(require_user)):
    svc = get_registry().get_service(name)
    if svc is None:
        raise HTTPException(status_code=404, detail="Service not running.")
    svc.stop_dataset_capture()
    return {"dataset_capture": False}


# ── TCP push server management ────────────────────────────────────────────────

class TcpPushStartRequest(BaseModel):
    host: str = "0.0.0.0"
    port: int
    certfile: str = ""
    keyfile: str = ""
    ca_certs: str = ""


@router.post("/services/{name}/tcp/start")
def start_tcp_push(name: str, req: TcpPushStartRequest,
                   _user: dict = Depends(require_user)):
    reg = get_registry()
    cfg = reg.get_config(name)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Service '{name}' not found.")
    err = get_tcp_registry().start(
        service_name=name,
        host=req.host,
        port=req.port,
        certfile=req.certfile or None,
        keyfile=req.keyfile or None,
        ca_certs=req.ca_certs or None,
    )
    if err:
        raise HTTPException(status_code=400, detail=err)
    from dataclasses import replace
    reg.upsert_config(replace(cfg,
        tcp_push_enabled=True,
        tcp_push_host=req.host,
        tcp_push_port=req.port,
        tcp_push_certfile=req.certfile,
        tcp_push_keyfile=req.keyfile,
        tcp_push_ca_certs=req.ca_certs,
    ))
    return {"tcp_push": True, "port": req.port}


@router.post("/services/{name}/tcp/stop")
def stop_tcp_push(name: str, _user: dict = Depends(require_user)):
    get_tcp_registry().stop(name)
    return {"tcp_push": False}


@router.get("/tcp/status")
def tcp_status(_user: dict = Depends(require_user)):
    return get_tcp_registry().get_status()


# ── SSE stream ────────────────────────────────────────────────────────────────

@router.get("/services/{name}/stream")
async def sse_stream(name: str, request: Request,
                     token: Optional[str] = None):
    """Server-Sent Events stream for live detection results.

    Authentication: pass JWT as ?token=<value> query param
    (Authorization header doesn't work well with EventSource in browsers).
    """
    from app.auth import _SECRET, _ALGORITHM
    from jose import JWTError, jwt as _jwt
    from app.config import get_config
    if not token:
        raise HTTPException(status_code=401, detail="Missing token.")
    try:
        _jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])
    except JWTError:
        if not get_config().validate_token(token):
            raise HTTPException(status_code=401, detail="Invalid token.")

    reg = get_registry()
    if reg.get_config(name) is None:
        raise HTTPException(status_code=404, detail=f"Service '{name}' not found.")

    q: asyncio.Queue = asyncio.Queue(maxsize=50)

    # Register
    if name not in _sse_queues:
        _sse_queues[name] = []
    _sse_queues[name].append(q)

    async def generator() -> AsyncGenerator[dict, None]:
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=5.0)
                    yield {"data": json.dumps(payload)}
                except asyncio.TimeoutError:
                    # Send keepalive comment
                    yield {"comment": "keepalive"}
        finally:
            try:
                _sse_queues[name].remove(q)
            except ValueError:
                pass

    return EventSourceResponse(generator())


# ── Result receiver (built-in push endpoint for services) ─────────────────────

@router.post("/results")
async def receive_result(request: Request):
    """Internal endpoint — detection services POST results here.
    Fans out to SSE subscribers and TCP push clients.
    This endpoint is intentionally open (no token) so services can push without auth.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON.")

    service_name = payload.get("service_name", "unknown")
    _do_notify(service_name, payload)
    return {"received": True}


@router.get("/results/all")
def get_all_results(_user: dict = Depends(require_user)):
    """Return last N results per service (from in-memory buffer)."""
    return _result_buffer


@router.delete("/results/all")
def clear_all_results(_user: dict = Depends(require_user)):
    """Clear the in-memory result buffer for all services."""
    _result_buffer.clear()
    return {"cleared": True}


@router.delete("/results/{name}")
def clear_service_results(name: str, _user: dict = Depends(require_user)):
    """Clear the in-memory result buffer for a single service."""
    _result_buffer.pop(name, None)
    return {"cleared": name}


# Simple in-memory result buffer (last 100 per service)
from collections import deque
_result_buffer: dict[str, deque] = {}


@router.post("/results/buffer")
async def buffer_result(request: Request):
    """Same as /results but also stores in buffer for polling."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON.")
    service_name = payload.get("service_name", "unknown")
    if service_name not in _result_buffer:
        _result_buffer[service_name] = deque(maxlen=100)
    _result_buffer[service_name].appendleft(payload)
    _do_notify(service_name, payload)
    return {"received": True}
