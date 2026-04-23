"""Auth endpoints — login, me, change password."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth import authenticate_user, create_access_token, require_user, require_admin
from app.db import list_users, update_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/login")
def login(req: LoginRequest):
    user = authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
        )
    token = create_access_token(user["username"], user["role"])
    return {"access_token": token, "token_type": "bearer", "role": user["role"], "username": user["username"]}


@router.get("/me")
def me(current_user: dict = Depends(require_user)):
    return current_user


@router.post("/change-password")
def change_password(req: ChangePasswordRequest, current_user: dict = Depends(require_user)):
    user = authenticate_user(current_user["username"], req.current_password)
    if not user:
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters.")
    update_password(current_user["username"], req.new_password)
    return {"ok": True}


@router.get("/users")
def get_users(_admin: dict = Depends(require_admin)):
    return list_users()
