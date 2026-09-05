"""System / config API endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional

from app.auth import require_user, require_admin
from app.config import get_config
from app.version import VERSION

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/info")
def get_info(_user: dict = Depends(require_user)):
    cfg = get_config()
    return {
        "version": VERSION,
        "config_path": str(cfg.path),
        "server": cfg.to_dict(),
    }


# ── API token management ───────────────────────────────────────────────────────

class TokenCreateRequest(BaseModel):
    label: str
    services: List[str] = Field(default_factory=list)
    permissions: List[str] = Field(default_factory=lambda: ["stream", "results"])


@router.get("/tokens")
def list_tokens(_user: dict = Depends(require_admin)):
    cfg = get_config()
    return [
        {
            "label": t["label"],
            "token": t["token"],
            "created_at": t.get("created_at", ""),
            "services": t.get("services", []),
            "permissions": t.get("permissions", ["stream", "results", "control"]),
        }
        for t in cfg.get_tokens()
    ]


@router.post("/tokens", status_code=201)
def create_token(req: TokenCreateRequest, _user: dict = Depends(require_admin)):
    cfg = get_config()
    token = cfg.create_token(req.label, services=req.services, permissions=req.permissions)
    from datetime import datetime, timezone
    return {
        "label": req.label,
        "token": token,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "services": req.services,
        "permissions": req.permissions,
    }


@router.delete("/tokens/{token_value}")
def revoke_token(token_value: str, _user: dict = Depends(require_admin)):
    cfg = get_config()
    if not cfg.revoke_token(token_value):
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
def get_settings(_user: dict = Depends(require_user)):
    return get_config().to_dict()


@router.patch("/settings")
def update_settings(req: ServerSettingsUpdate, _user: dict = Depends(require_admin)):
    get_config().update(req.model_dump(exclude_none=True))
    return get_config().to_dict()
