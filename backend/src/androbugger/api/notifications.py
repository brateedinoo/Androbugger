"""Notification REST endpoints, WebSocket push, and shared create helper."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from androbugger.auth.middleware import get_current_user
from androbugger.db.database import get_db

router = APIRouter(prefix="/api/notifications", tags=["notifications"])
logger = logging.getLogger(__name__)

# Connected notification WebSocket clients: {user_id: [ws, ...]}
_ws_clients: dict[str, list[WebSocket]] = {}
_ws_lock = asyncio.Lock()


# ── Shared helper (called by scheduler, diagnostic pipeline, etc.) ─────────────

async def create_notification(
    kind: str,
    title: str,
    body: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    device_serial: str | None = None,
) -> int:
    """Insert a notification and push it to connected WS clients."""
    now = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        cursor = await db.execute(
            """INSERT INTO notifications (user_id, kind, title, body, session_id, device_serial, read, created_at)
               VALUES (?, ?, ?, ?, ?, ?, FALSE, ?)""",
            (user_id, kind, title, body, session_id, device_serial, now),
        )
        notif_id = cursor.lastrowid
        await db.commit()

    payload = json.dumps({
        "type": "notification",
        "id": notif_id,
        "kind": kind,
        "title": title,
        "body": body,
        "session_id": session_id,
        "device_serial": device_serial,
        "created_at": now,
    })

    # Push to all relevant clients
    async with _ws_lock:
        targets: list[WebSocket] = []
        if user_id and user_id in _ws_clients:
            targets.extend(_ws_clients[user_id])
        # Broadcast (user_id=None) goes to everyone
        if user_id is None:
            for clients in _ws_clients.values():
                targets.extend(clients)

    for ws in targets:
        try:
            await ws.send_text(payload)
        except Exception:
            pass

    return notif_id


# ── REST endpoints ─────────────────────────────────────────────────────────────

@router.get("")
async def list_notifications(
    user: Annotated[dict, Depends(get_current_user)],
    unread_only: bool = False,
    limit: int = 20,
):
    uid = user["id"]
    if unread_only:
        where = "WHERE (user_id=? OR user_id IS NULL) AND read=FALSE"
    else:
        where = "WHERE (user_id=? OR user_id IS NULL)"

    async with get_db() as db:
        rows = await (await db.execute(
            f"SELECT * FROM notifications {where} ORDER BY created_at DESC LIMIT ?",
            (uid, limit),
        )).fetchall()
        unread_row = await (await db.execute(
            "SELECT COUNT(*) FROM notifications WHERE (user_id=? OR user_id IS NULL) AND read=FALSE",
            (uid,),
        )).fetchone()

    return {
        "notifications": [dict(r) for r in rows],
        "unread_count": unread_row[0],
    }


@router.post("/{notif_id}/read")
async def mark_read(notif_id: int, user: Annotated[dict, Depends(get_current_user)]):
    async with get_db() as db:
        await db.execute(
            "UPDATE notifications SET read=TRUE WHERE id=? AND (user_id=? OR user_id IS NULL)",
            (notif_id, user["id"]),
        )
        await db.commit()
    return {"ok": True}


@router.post("/read-all")
async def mark_all_read(user: Annotated[dict, Depends(get_current_user)]):
    async with get_db() as db:
        result = await db.execute(
            "UPDATE notifications SET read=TRUE WHERE (user_id=? OR user_id IS NULL) AND read=FALSE",
            (user["id"],),
        )
        await db.commit()
    return {"updated": result.rowcount}


@router.delete("/{notif_id}")
async def delete_notification(notif_id: int, user: Annotated[dict, Depends(get_current_user)]):
    async with get_db() as db:
        await db.execute(
            "DELETE FROM notifications WHERE id=? AND (user_id=? OR user_id IS NULL)",
            (notif_id, user["id"]),
        )
        await db.commit()
    return {"ok": True}


# ── WebSocket push ─────────────────────────────────────────────────────────────

@router.websocket("/ws/notifications")
async def ws_notifications(websocket: WebSocket):
    """Authenticate via token query param, then stream notification events."""
    token = websocket.query_params.get("token", "")

    # Validate token
    try:
        from androbugger.auth.middleware import _decode_token
        payload = _decode_token(token)
        user_id: str = payload["sub"]
    except Exception:
        await websocket.close(code=4001)
        return

    await websocket.accept()

    async with _ws_lock:
        _ws_clients.setdefault(user_id, []).append(websocket)

    # Send unread count on connect
    try:
        async with get_db() as db:
            row = await (await db.execute(
                "SELECT COUNT(*) FROM notifications WHERE (user_id=? OR user_id IS NULL) AND read=FALSE",
                (user_id,),
            )).fetchone()
        await websocket.send_text(json.dumps({"type": "unread_count", "count": row[0]}))
    except Exception:
        pass

    try:
        while True:
            # Ping every 30s to keep connection alive
            await asyncio.sleep(30)
            await websocket.send_text(json.dumps({"type": "ping"}))
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        async with _ws_lock:
            clients = _ws_clients.get(user_id, [])
            if websocket in clients:
                clients.remove(websocket)
            if not clients:
                _ws_clients.pop(user_id, None)
