"""Authentication endpoints."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from androbugger.auth.middleware import create_access_token, create_refresh_token, get_current_user
from androbugger.auth.users import get_user_by_id, update_last_login, verify_password
from androbugger.db.audit import log as audit_log

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(body: LoginRequest, request: Request):
    user = await verify_password(body.username, body.password)
    ip = request.client.host if request.client else None
    if not user:
        await audit_log("login_failed", "warning", detail={"username": body.username}, ip_address=ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    await update_last_login(user["id"])
    await audit_log("login", "info", user_id=user["id"], ip_address=ip)

    return {
        "token": create_access_token(user["id"], user["username"], user["role"]),
        "refresh_token": create_refresh_token(user["id"]),
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "force_password_change": bool(user["force_password_change"]),
        },
    }


@router.post("/logout")
async def logout(user: Annotated[dict, Depends(get_current_user)]):
    await audit_log("logout", "info", user_id=user["id"])
    return {"ok": True}


@router.get("/me")
async def me(user: Annotated[dict, Depends(get_current_user)]):
    full = await get_user_by_id(user["id"])
    if not full:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": full["id"],
        "username": full["username"],
        "role": full["role"],
        "force_password_change": bool(full["force_password_change"]),
        "last_login": full["last_login"],
    }
