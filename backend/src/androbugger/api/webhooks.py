"""Webhook endpoint management and delivery history."""
import json
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl

from androbugger.auth.middleware import require_role
from androbugger.db.database import get_db
from androbugger.integrations.webhook_dispatcher import test_endpoint

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

VALID_EVENTS = {
    "session.completed", "session.failed",
    "hardware.alert", "regression.detected", "plugin.error",
}


class WebhookCreate(BaseModel):
    name: str
    url: str
    secret: str = ""
    events: list[str] = []
    enabled: bool = True


class WebhookUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    secret: str | None = None
    events: list[str] | None = None
    enabled: bool | None = None


@router.get("")
async def list_webhooks(user: Annotated[dict, Depends(require_role("admin"))]):
    async with get_db() as db:
        rows = await (await db.execute(
            "SELECT id, name, url, events, enabled, created_at FROM webhook_endpoints"
            " ORDER BY created_at DESC"
        )).fetchall()
    return {"webhooks": [dict(r) for r in rows]}


@router.post("")
async def create_webhook(
    body: WebhookCreate,
    user: Annotated[dict, Depends(require_role("admin"))],
):
    invalid = [e for e in body.events if e not in VALID_EVENTS]
    if invalid:
        raise HTTPException(400, f"Unknown events: {invalid}")

    wid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        await db.execute(
            "INSERT INTO webhook_endpoints (id, name, url, secret, events, enabled, created_by, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (wid, body.name, body.url, body.secret, json.dumps(body.events), body.enabled,
             user["id"], now),
        )
        await db.commit()
    return {"webhook": {"id": wid, "name": body.name, "url": body.url,
                        "events": body.events, "enabled": body.enabled}}


@router.get("/{wid}")
async def get_webhook(wid: str, user: Annotated[dict, Depends(require_role("admin"))]):
    async with get_db() as db:
        row = await (await db.execute(
            "SELECT id, name, url, events, enabled, created_at FROM webhook_endpoints WHERE id=?",
            (wid,),
        )).fetchone()
    if not row:
        raise HTTPException(404, "Webhook not found")
    return {"webhook": dict(row)}


@router.put("/{wid}")
async def update_webhook(
    wid: str,
    body: WebhookUpdate,
    user: Annotated[dict, Depends(require_role("admin"))],
):
    async with get_db() as db:
        row = await (await db.execute(
            "SELECT id FROM webhook_endpoints WHERE id=?", (wid,)
        )).fetchone()
        if not row:
            raise HTTPException(404, "Webhook not found")

        if body.name is not None:
            await db.execute("UPDATE webhook_endpoints SET name=? WHERE id=?", (body.name, wid))
        if body.url is not None:
            await db.execute("UPDATE webhook_endpoints SET url=? WHERE id=?", (body.url, wid))
        if body.secret is not None:
            await db.execute("UPDATE webhook_endpoints SET secret=? WHERE id=?", (body.secret, wid))
        if body.events is not None:
            invalid = [e for e in body.events if e not in VALID_EVENTS]
            if invalid:
                raise HTTPException(400, f"Unknown events: {invalid}")
            await db.execute(
                "UPDATE webhook_endpoints SET events=? WHERE id=?",
                (json.dumps(body.events), wid),
            )
        if body.enabled is not None:
            await db.execute(
                "UPDATE webhook_endpoints SET enabled=? WHERE id=?", (body.enabled, wid)
            )
        await db.commit()
    return {"ok": True}


@router.delete("/{wid}")
async def delete_webhook(wid: str, user: Annotated[dict, Depends(require_role("admin"))]):
    async with get_db() as db:
        await db.execute("DELETE FROM webhook_endpoints WHERE id=?", (wid,))
        await db.commit()
    return {"ok": True}


@router.get("/{wid}/deliveries")
async def list_deliveries(
    wid: str,
    limit: int = 50,
    user: Annotated[dict, Depends(require_role("admin"))] = None,
):
    async with get_db() as db:
        rows = await (await db.execute(
            "SELECT id, event, response_status, delivered_at, error, attempts"
            " FROM webhook_deliveries WHERE endpoint_id=?"
            " ORDER BY id DESC LIMIT ?",
            (wid, limit),
        )).fetchall()
    return {"deliveries": [dict(r) for r in rows]}


@router.post("/{wid}/test")
async def test_webhook(wid: str, user: Annotated[dict, Depends(require_role("admin"))]):
    result = await test_endpoint(wid)
    return result
