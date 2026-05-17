"""JWT authentication middleware and FastAPI dependencies."""
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from androbugger.auth.roles import role_gte
from androbugger.config import settings

_ALGORITHM = "HS256"
_bearer = HTTPBearer(auto_error=False)


def create_access_token(user_id: str, username: str, role: str) -> str:
    expire = datetime.now(UTC) + timedelta(hours=settings.access_token_expire_hours)
    return jwt.encode(
        {"sub": user_id, "username": username, "role": role, "exp": expire, "type": "access"},
        settings.secret_key,
        algorithm=_ALGORITHM,
    )


def create_refresh_token(user_id: str) -> str:
    expire = datetime.now(UTC) + timedelta(hours=settings.refresh_token_expire_hours)
    return jwt.encode(
        {"sub": user_id, "exp": expire, "type": "refresh"},
        settings.secret_key,
        algorithm=_ALGORITHM,
    )


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc


def decode_access_token(token: str) -> dict | None:
    """Decode an access JWT for non-HTTP contexts (e.g. WebSocket query params).

    Returns the user dict on success, or None if the token is missing/invalid/wrong-type.
    Never raises — callers handle the None case themselves (WS close with policy code).
    """
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])
    except JWTError:
        return None
    if payload.get("type") != "access":
        return None
    return {"id": payload["sub"], "username": payload["username"], "role": payload["role"]}


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> dict:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = _decode_token(credentials.credentials)
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong token type")
    return {"id": payload["sub"], "username": payload["username"], "role": payload["role"]}


def require_role(min_role: str):
    async def _check(user: Annotated[dict, Depends(get_current_user)]) -> dict:
        if not role_gte(user["role"], min_role):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user
    return _check
