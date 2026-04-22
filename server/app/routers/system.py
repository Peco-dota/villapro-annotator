"""System / config API endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.auth import require_token
from app.config import get_config
from app.version import VERSION

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/info")
def get_info(_token: str = Depends(require_token)):
    cfg = get_config()
    return {
        "version": VERSION,
        "config_path": str(cfg.path),
        "server": cfg.to_dict(),
        "token_count": len(cfg.get_tokens()),
    }


# ── API token management ──────────────────────────────────────────────────────

class TokenCreateRequest(BaseModel):
    name: str


class TokenRevokeRequest(BaseModel):
    token: str


@router.get("/tokens")
def list_tokens(_token: str = Depends(require_token)):
    cfg = get_config()
    return [{"name": t["name"]} for t in cfg.get_tokens()]


@router.post("/tokens", status_code=201)
def create_token(req: TokenCreateRequest, _token: str = Depends(require_token)):
    cfg = get_config()
    token = cfg.create_token(req.name)
    return {"name": req.name, "token": token}


@router.delete("/tokens")
def revoke_token(req: TokenRevokeRequest, _token: str = Depends(require_token)):
    cfg = get_config()
    if not cfg.revoke_token(req.token):
        raise HTTPException(status_code=404, detail="Token not found.")
    return {"revoked": True}


# ── Server settings ───────────────────────────────────────────────────────────

class ServerSettingsUpdate(BaseModel):
    host: Optional[str] = None
    port: Optional[int] = None
    ssl_certfile: Optional[str] = None
    ssl_keyfile: Optional[str] = None
    result_receiver_host: Optional[str] = None
    result_receiver_port: Optional[int] = None


@router.get("/settings")
def get_settings(_token: str = Depends(require_token)):
    return get_config().to_dict()


@router.patch("/settings")
def update_settings(req: ServerSettingsUpdate, _token: str = Depends(require_token)):
    get_config().update(req.model_dump(exclude_none=True))
    return get_config().to_dict()
