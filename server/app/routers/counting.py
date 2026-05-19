"""Counting services API — manage parking-occupancy counters, SSE stream."""
from __future__ import annotations

import asyncio
import json
from collections import deque
from typing import Optional, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.auth import require_user
from app.counting_service import (
    get_counting_registry, CountingConfig,
    STATE_RUNNING,
)
from app.tcp_push import get_tcp_registry

router = APIRouter(prefix="/api/counting", tags=["counting"])

# SSE subscribers: counter_name → list of asyncio queues
_counting_sse_queues: dict[str, list[asyncio.Queue]] = {}

# In-memory result buffer for polling: counter_name → deque of payloads
_counting_result_buffer: dict[str, deque] = {}

# Event loop reference — set from main.py lifespan alongside detection
_event_loop: asyncio.AbstractEventLoop | None = None


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _event_loop
    _event_loop = loop


def _notify_counting_sse(service_name: str, payload: dict) -> None:
    """Called from counting service callbacks (any thread) to fan-out to SSE."""
    if _event_loop is None or _event_loop.is_closed():
        return
    _event_loop.call_soon_threadsafe(_do_notify_counting, service_name, payload)


def _do_notify_counting(service_name: str, payload: dict) -> None:
    """Runs on the asyncio event loop: push to SSE queues and TCP clients."""
    for q in list(_counting_sse_queues.get(service_name, [])):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass
    get_tcp_registry().push(service_name, payload)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cfg_to_dict(cfg: CountingConfig, registry) -> dict:
    d = cfg.to_dict()
    d["state"] = registry.get_state(cfg.name)
    svc = registry.get_service(cfg.name)
    if svc:
        d.update(svc.get_counts())
    else:
        d["count"] = 0
        d["last_reset"] = ""
    d["tcp_push_running"] = get_tcp_registry().is_running(cfg.name)
    return d


# ── Config CRUD ───────────────────────────────────────────────────────────────

class CountingConfigIn(BaseModel):
    name: str
    source_service: str
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


@router.get("/services")
def list_services(_user: dict = Depends(require_user)):
    reg = get_counting_registry()
    return [_cfg_to_dict(c, reg) for c in reg.get_configs()]


@router.get("/services/{name}")
def get_service(name: str, _user: dict = Depends(require_user)):
    reg = get_counting_registry()
    cfg = reg.get_config(name)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Counter '{name}' not found.")
    return _cfg_to_dict(cfg, reg)


@router.post("/services", status_code=201)
def create_or_update_service(req: CountingConfigIn, _user: dict = Depends(require_user)):
    cfg = CountingConfig(
        name=req.name,
        source_service=req.source_service,
        auto_start=req.auto_start,
        tcp_push_enabled=req.tcp_push_enabled,
        tcp_push_host=req.tcp_push_host,
        tcp_push_port=req.tcp_push_port,
        tcp_push_certfile=req.tcp_push_certfile,
        tcp_push_keyfile=req.tcp_push_keyfile,
        tcp_push_ca_certs=req.tcp_push_ca_certs,
        initial_count=req.initial_count,
        output_host=req.output_host,
        output_port=req.output_port,
    )
    get_counting_registry().upsert_config(cfg)
    return _cfg_to_dict(cfg, get_counting_registry())


@router.delete("/services/{name}")
def delete_service(name: str, _user: dict = Depends(require_user)):
    reg = get_counting_registry()
    if reg.get_config(name) is None:
        raise HTTPException(status_code=404, detail=f"Counter '{name}' not found.")
    get_tcp_registry().stop(name)
    reg.remove_config(name)
    return {"deleted": name}


# ── Start / stop ──────────────────────────────────────────────────────────────

@router.post("/services/{name}/start")
def start_service(name: str, _user: dict = Depends(require_user)):
    reg = get_counting_registry()
    _counting_result_buffer.pop(name, None)
    err = reg.start(name)
    if err:
        raise HTTPException(status_code=400, detail=err)
    return {"started": name, "state": reg.get_state(name)}


@router.post("/services/{name}/stop")
def stop_service(name: str, _user: dict = Depends(require_user)):
    reg = get_counting_registry()
    if reg.get_config(name) is None:
        raise HTTPException(status_code=404, detail=f"Counter '{name}' not found.")
    reg.stop(name)
    return {"stopped": name, "state": reg.get_state(name)}


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/services/{name}/status")
def get_service_status(name: str, _user: dict = Depends(require_user)):
    reg = get_counting_registry()
    cfg = reg.get_config(name)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Counter '{name}' not found.")
    svc = reg.get_service(name)
    return {
        "name": name,
        "source_service": cfg.source_service,
        "state": reg.get_state(name),
        "running": reg.get_state(name) == STATE_RUNNING,
        "tcp_push_running": get_tcp_registry().is_running(name),
        **(svc.get_counts() if svc else {"count": 0, "last_reset": ""}),
    }


@router.get("/services/{name}/result")
def get_service_result(name: str, _user: dict = Depends(require_user)):
    """Return the last counting result for this counter (same payload as SSE/TCP push)."""
    reg = get_counting_registry()
    if reg.get_config(name) is None:
        raise HTTPException(status_code=404, detail=f"Counter '{name}' not found.")
    buf = _counting_result_buffer.get(name)
    if buf:
        return buf[0]
    svc = reg.get_service(name)
    return {"service_name": name, "available": False, **(svc.get_counts() if svc else {})}


# ── Reset ─────────────────────────────────────────────────────────────────────

@router.post("/services/{name}/reset")
def reset_counts(name: str, _user: dict = Depends(require_user)):
    reg = get_counting_registry()
    svc = reg.get_service(name)
    if svc is None:
        raise HTTPException(status_code=404, detail=f"Counter '{name}' is not running.")
    svc.reset_counts()
    return {"reset": True, **svc.get_counts()}


# ── SSE stream ────────────────────────────────────────────────────────────────

@router.get("/services/{name}/stream")
async def sse_stream(name: str, request: Request, token: Optional[str] = None):
    """Server-Sent Events stream for live counting results.

    Authentication: pass JWT as ?token=<value> (same as detection SSE).
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

    reg = get_counting_registry()
    if reg.get_config(name) is None:
        raise HTTPException(status_code=404, detail=f"Counter '{name}' not found.")

    q: asyncio.Queue = asyncio.Queue(maxsize=50)
    _counting_sse_queues.setdefault(name, []).append(q)

    async def generator() -> AsyncGenerator[dict, None]:
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=5.0)
                    yield {"data": json.dumps(payload)}
                except asyncio.TimeoutError:
                    yield {"comment": "keepalive"}
        finally:
            try:
                _counting_sse_queues[name].remove(q)
            except ValueError:
                pass

    return EventSourceResponse(generator())


# ── Result buffer (polling fallback) ─────────────────────────────────────────

@router.get("/results/all")
def get_all_results(_user: dict = Depends(require_user)):
    """Return the last 100 counting events per counter (polling fallback)."""
    return {k: list(v) for k, v in _counting_result_buffer.items()}


# ── TCP push management ───────────────────────────────────────────────────────

class TcpPushStartRequest(BaseModel):
    host: str = "0.0.0.0"
    port: int
    certfile: str = ""
    keyfile: str = ""
    ca_certs: str = ""


@router.post("/services/{name}/tcp/start")
def start_tcp_push(name: str, req: TcpPushStartRequest,
                   _user: dict = Depends(require_user)):
    reg = get_counting_registry()
    cfg = reg.get_config(name)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Counter '{name}' not found.")
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
    reg = get_counting_registry()
    cfg = reg.get_config(name)
    get_tcp_registry().stop(name)
    if cfg is not None:
        from dataclasses import replace
        reg.upsert_config(replace(cfg, tcp_push_enabled=False))
    return {"tcp_push": False}
