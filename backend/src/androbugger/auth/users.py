"""User CRUD operations."""
import uuid
from datetime import UTC, datetime

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from androbugger.db.database import get_db

_ph = PasswordHasher()


async def get_user_by_username(username: str) -> dict | None:
    async with get_db() as db:
        row = await (
            await db.execute("SELECT * FROM users WHERE username=?", (username,))
        ).fetchone()
        return dict(row) if row else None


async def get_user_by_id(user_id: str) -> dict | None:
    async with get_db() as db:
        row = await (
            await db.execute("SELECT * FROM users WHERE id=?", (user_id,))
        ).fetchone()
        return dict(row) if row else None


async def verify_password(username: str, password: str) -> dict | None:
    user = await get_user_by_username(username)
    if not user:
        return None
    try:
        _ph.verify(user["password_hash"], password)
        return user
    except VerifyMismatchError:
        return None


async def create_user(username: str, password: str, role: str) -> dict:
    user_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    async with get_db() as db:
        await db.execute(
            """INSERT INTO users (id, username, password_hash, role, force_password_change, created_at)
               VALUES (?, ?, ?, ?, FALSE, ?)""",
            (user_id, username, _ph.hash(password), role, now),
        )
        await db.commit()
    return {"id": user_id, "username": username, "role": role}


async def update_last_login(user_id: str) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET last_login=? WHERE id=?",
            (datetime.now(UTC).isoformat(), user_id),
        )
        await db.commit()


async def change_password(user_id: str, new_password: str) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET password_hash=?, force_password_change=FALSE WHERE id=?",
            (_ph.hash(new_password), user_id),
        )
        await db.commit()
