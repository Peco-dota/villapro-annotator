"""Authentication for VisionQ server — JWT-based username/password login.

All protected endpoints use:
    current_user: dict = Depends(require_user)
    # or for admin-only:
    current_user: dict = Depends(require_admin)

The JWT is passed as:
    Authorization: Bearer <token>

---
NOTE: The original API token system has been commented out below.
      It can be re-enabled if programmatic/script access is needed in the future.
      See: app/config.py get_tokens() / validate_token() / create_token() / revoke_token()
      And: app/routers/system.py token management endpoints
---
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

from app.db import get_user, verify_password

_bearer = HTTPBearer(auto_error=False)

_DEFAULT_SECRET = "visionq-dev-secret-change-in-production"
_SECRET = os.environ.get("VISIONQ_SECRET", _DEFAULT_SECRET)
_ALGORITHM = "HS256"

if _SECRET == _DEFAULT_SECRET:
    import logging as _logging
    _logging.getLogger("visionq").warning(
        "VISIONQ_SECRET is not set — using the default dev secret. "
        "Set VISIONQ_SECRET in your environment before deploying."
    )
_TOKEN_EXPIRE_HOURS = 24 * 7  # 1 week


def create_access_token(username: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=_TOKEN_EXPIRE_HOURS)
    return jwt.encode(
        {"sub": username, "role": role, "exp": expire},
        _SECRET,
        algorithm=_ALGORITHM,
    )


def authenticate_user(username: str, password: str) -> Optional[dict]:
    user = get_user(username)
    if not user:
        return None
    if not verify_password(password, user["hashed_password"]):
        return None
    return user


def require_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    token: Optional[str] = Query(default=None),
) -> dict:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing token.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    # Accept token from Authorization header or ?token= query param (for <img src> URLs)
    raw = token
    if not raw and credentials and credentials.scheme.lower() == "bearer":
        raw = credentials.credentials
    if not raw:
        raise exc

    # Try JWT first
    try:
        payload = jwt.decode(raw, _SECRET, algorithms=[_ALGORITHM])
        username: str = payload.get("sub", "")
        role: str = payload.get("role", "customer")
        if not username:
            raise exc
        return {"username": username, "role": role}
    except JWTError:
        pass

    # Fall back to API token
    from app.config import get_config
    record = get_config().validate_token(raw)
    if record:
        return {
            "username": record["label"],
            "role": "api_token",
            "services": record.get("services", []),
            "permissions": record.get("permissions", ["stream", "results", "control"]),
        }

    raise exc


def require_admin(current_user: dict = Depends(require_user)) -> dict:
    if current_user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
    return current_user


def check_service_access(user: dict, service_name: str, permission: str) -> bool:
    """Return True if the user (JWT or API token) can access the service with the given permission.

    JWT admins always pass. API token users are checked against their services and permissions lists.
    An empty services list means access to all services.
    """
    if user.get("role") != "api_token":
        return True
    allowed_services: list = user.get("services", [])
    if allowed_services and service_name not in allowed_services:
        return False
    allowed_perms: list = user.get("permissions", ["stream", "results", "control"])
    return permission in allowed_perms


# ── Legacy API token system (commented out — keep for future re-enablement) ───
#
# from fastapi import Security
# from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
# from app.config import get_config
#
# _bearer = HTTPBearer(auto_error=False)
#
# def require_token(
#     credentials: Optional[HTTPAuthorizationCredentials] = Security(_bearer),
# ) -> str:
#     config = get_config()
#     if not config.get_tokens():
#         return "__bootstrap__"
#     token: Optional[str] = None
#     if credentials and credentials.scheme.lower() == "bearer":
#         token = credentials.credentials
#     if not token or not config.validate_token(token):
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Invalid or missing API token.",
#             headers={"WWW-Authenticate": "Bearer"},
#         )
#     return token
