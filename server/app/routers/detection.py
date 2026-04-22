"""Detection services API — manage YOLO inference services, SSE stream, TCP push."""
import asyncio
import json
import os
from typing import Optional, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.auth import require_token
from app.detection_service import (
    get_registry, ServiceConfig,
    STATE_STOPPED, STATE_LOADING, STATE_RUNNING, STATE_ERROR,
)
from app.tcp_push import get_tcp_registry

router = APIRouter(prefix="/api/detection", tags=["detection"])

# SSE subscribers: service_name -> list of asyncio queues
_sse_queues: dict[str, list[asyncio.Queue]] = {}
_sse_lock = asyncio.Lock()


def _notify_sse(service_name: str, payload: dict):
    """Called from detection service threads to fan-out to SSE subscribers.

    This is safe to call from a background thread — we schedule the coroutine
    onto the running event loop.
    """
    import asyncio as _asyncio
    try:
        loop = _asyncio.get_event_loop()
    except RuntimeError:
        return
    loop.call_soon_threadsafe(_do_notify, service_name, payload)


def _do_notify(service_name: str, payload: dict):
    queues = _sse_queues.get(service_name, [])
    for q in list(queues):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass
    # Also push to TCP clients
    get_tcp_registry().push(service_name, payload)


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
    gate_area_threshold: float = 0.0
    # TCP push settings
    tcp_push_enabled: bool = False
    tcp_push_host: str = "0.0.0.0"
    tcp_push_port: int = 0
    tcp_push_certfile: str = ""
    tcp_push_keyfile: str = ""
    tcp_push_ca_certs: str = ""


def _cfg_to_dict(cfg: ServiceConfig, registry) -> dict:
    d = cfg.to_dict()
    d["state"] = registry.get_state(cfg.name)
    d["log"] = [str(e) for e in (registry.get_service(cfg.name).get_log_entries()
                                  if registry.get_service(cfg.name) else [])]
    tcp_reg = get_tcp_registry()
    d["tcp_push_running"] = tcp_reg.is_running(cfg.name)
    return d


@router.get("/services")
def list_services(_token: str = Depends(require_token)):
    reg = get_registry()
    return [_cfg_to_dict(c, reg) for c in reg.get_configs()]


@router.get("/services/{name}")
def get_service(name: str, _token: str = Depends(require_token)):
    reg = get_registry()
    cfg = reg.get_config(name)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Service '{name}' not found.")
    return _cfg_to_dict(cfg, reg)


@router.post("/services", status_code=201)
def create_or_update_service(req: ServiceConfigIn, _token: str = Depends(require_token)):
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
        gate_area_threshold=req.gate_area_threshold,
    )
    get_registry().upsert_config(cfg)
    return _cfg_to_dict(cfg, get_registry())


@router.delete("/services/{name}")
def delete_service(name: str, _token: str = Depends(require_token)):
    reg = get_registry()
    if reg.get_config(name) is None:
        raise HTTPException(status_code=404, detail=f"Service '{name}' not found.")
    get_tcp_registry().stop(name)
    reg.remove_config(name)
    return {"deleted": name}


# ── Start / stop ──────────────────────────────────────────────────────────────

@router.post("/services/{name}/start")
def start_service(name: str, _token: str = Depends(require_token)):
    reg = get_registry()

    def _on_done(error: str):
        pass  # SSE subscribers will see state change on next poll

    err = reg.start_async(name, _on_done)
    if err:
        raise HTTPException(status_code=400, detail=err)
    return {"started": name, "state": reg.get_state(name)}


@router.post("/services/{name}/stop")
def stop_service(name: str, _token: str = Depends(require_token)):
    reg = get_registry()
    if reg.get_config(name) is None:
        raise HTTPException(status_code=404, detail=f"Service '{name}' not found.")
    reg.stop(name)
    return {"stopped": name, "state": reg.get_state(name)}


@router.post("/services/{name}/restart")
def restart_service(name: str, _token: str = Depends(require_token)):
    reg = get_registry()

    def _on_done(error: str):
        pass

    err = reg.restart_async(name, _on_done)
    if err:
        raise HTTPException(status_code=400, detail=err)
    return {"restarted": name, "state": reg.get_state(name)}


# ── Service status & log ──────────────────────────────────────────────────────

@router.get("/services/{name}/status")
def get_service_status(name: str, _token: str = Depends(require_token)):
    reg = get_registry()
    cfg = reg.get_config(name)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Service '{name}' not found.")
    svc = reg.get_service(name)
    return {
        "name": name,
        "state": reg.get_state(name),
        "error": svc.error_msg if svc else "",
        "is_recording": svc.is_recording if svc else False,
        "is_previewing": svc.is_previewing if svc else False,
        "is_direction_debugging": svc.is_direction_debugging if svc else False,
    }


@router.get("/services/{name}/log")
def get_service_log(name: str, _token: str = Depends(require_token)):
    reg = get_registry()
    svc = reg.get_service(name)
    if svc is None:
        return {"name": name, "log": []}
    return {"name": name, "log": [str(e) for e in svc.get_log_entries()]}


# ── Recording ─────────────────────────────────────────────────────────────────

@router.post("/services/{name}/recording/start")
def start_recording(name: str, record_dir: Optional[str] = None,
                    _token: str = Depends(require_token)):
    svc = get_registry().get_service(name)
    if svc is None:
        raise HTTPException(status_code=404, detail="Service not running.")
    err = svc.start_recording(record_dir)
    if err:
        raise HTTPException(status_code=400, detail=err)
    return {"recording": True}


@router.post("/services/{name}/recording/stop")
def stop_recording(name: str, _token: str = Depends(require_token)):
    svc = get_registry().get_service(name)
    if svc is None:
        raise HTTPException(status_code=404, detail="Service not running.")
    svc.stop_recording()
    return {"recording": False}


# ── Direction debug ───────────────────────────────────────────────────────────

@router.post("/services/{name}/debug/start")
def start_debug(name: str, path: Optional[str] = None,
                _token: str = Depends(require_token)):
    svc = get_registry().get_service(name)
    if svc is None:
        raise HTTPException(status_code=404, detail="Service not running.")
    if not path:
        import os as _os
        _os.makedirs(_os.path.expanduser("~/VisionQ_debug"), exist_ok=True)
        from datetime import datetime
        path = _os.path.expanduser(
            f"~/VisionQ_debug/{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
    svc.start_direction_debug(path)
    return {"debug_path": path}


@router.post("/services/{name}/debug/stop")
def stop_debug(name: str, _token: str = Depends(require_token)):
    svc = get_registry().get_service(name)
    if svc is None:
        raise HTTPException(status_code=404, detail="Service not running.")
    path = svc.stop_direction_debug()
    return {"debug_path": path}


# ── Video controls ────────────────────────────────────────────────────────────

@router.post("/services/{name}/video/pause")
def toggle_pause(name: str, _token: str = Depends(require_token)):
    svc = get_registry().get_service(name)
    if svc is None:
        raise HTTPException(status_code=404, detail="Service not running.")
    paused = svc.toggle_video_pause()
    return {"paused": paused}


@router.post("/services/{name}/video/speed")
def set_speed(name: str, speed: float, _token: str = Depends(require_token)):
    svc = get_registry().get_service(name)
    if svc is None:
        raise HTTPException(status_code=404, detail="Service not running.")
    svc.set_video_speed(speed)
    return {"speed": speed}


@router.post("/services/{name}/video/seek")
def seek_video(name: str, ms: Optional[float] = None,
               delta: Optional[float] = None, _token: str = Depends(require_token)):
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
def step_frame(name: str, _token: str = Depends(require_token)):
    svc = get_registry().get_service(name)
    if svc is None:
        raise HTTPException(status_code=404, detail="Service not running.")
    svc.step_video_frame()
    return {"ok": True}


@router.get("/services/{name}/video/state")
def get_video_state(name: str, _token: str = Depends(require_token)):
    svc = get_registry().get_service(name)
    if svc is None:
        raise HTTPException(status_code=404, detail="Service not running.")
    pos_ms, duration_ms, speed, paused = svc.get_video_state()
    return {"pos_ms": pos_ms, "duration_ms": duration_ms, "speed": speed, "paused": paused}


# ── TCP push server management ────────────────────────────────────────────────

class TcpPushStartRequest(BaseModel):
    host: str = "0.0.0.0"
    port: int
    certfile: str = ""
    keyfile: str = ""
    ca_certs: str = ""


@router.post("/services/{name}/tcp/start")
def start_tcp_push(name: str, req: TcpPushStartRequest,
                   _token: str = Depends(require_token)):
    reg = get_registry()
    if reg.get_config(name) is None:
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
    return {"tcp_push": True, "port": req.port}


@router.post("/services/{name}/tcp/stop")
def stop_tcp_push(name: str, _token: str = Depends(require_token)):
    get_tcp_registry().stop(name)
    return {"tcp_push": False}


@router.get("/tcp/status")
def tcp_status(_token: str = Depends(require_token)):
    return get_tcp_registry().get_status()


# ── SSE stream ────────────────────────────────────────────────────────────────

@router.get("/services/{name}/stream")
async def sse_stream(name: str, request: Request,
                     token: Optional[str] = None):
    """Server-Sent Events stream for live detection results.

    Authentication: pass token as ?token=<value> query param
    (Authorization header doesn't work well with EventSource in browsers).
    """
    from app.config import get_config
    cfg = get_config()
    if cfg.get_tokens() and not cfg.validate_token(token or ""):
        raise HTTPException(status_code=401, detail="Invalid or missing token.")

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
def get_all_results(_token: str = Depends(require_token)):
    """Return last N results per service (from in-memory buffer)."""
    return _result_buffer


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
