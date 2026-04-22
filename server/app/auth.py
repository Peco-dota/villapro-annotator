"""API token authentication for VisionQ server.

All protected endpoints require:
    Authorization: Bearer <token>
or
    X-API-Token: <token>

The first token creation endpoint is intentionally open so a freshly
installed server can bootstrap itself. After that, creating/revoking
tokens requires an existing valid token.
"""
from fastapi import Security, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import get_config

_bearer = HTTPBearer(auto_error=False)


def require_token(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> str:
    config = get_config()

    # No tokens configured yet — open access so the admin can bootstrap
    if not config.get_tokens():
        return "__bootstrap__"

    token: str | None = None
    if credentials and credentials.scheme.lower() == "bearer":
        token = credentials.credentials

    if not token or not config.validate_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token
