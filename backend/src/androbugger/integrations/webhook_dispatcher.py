"""Outbound webhook dispatcher — fire-and-forget with HMAC signatures and retry."""
import asyncio
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone

import httpx

from androbugger.config import settings
from androbugger.db.database import get_db

logger = logging.getLogger(__name__)


async def dispatch_event(event: str, payload: dict) -> None:
    """Fan out an event to all enabled webhook endpoints that subscribe to it."""
    async with get_db() as db:
        rows = await (await db.execute(
            "SELECT id, url, secret, events FROM webhook_endpoints WHERE enabled=TRUE"
        )).fetchall()

    for row in rows:
        subscribed = json.loads(row["events"] or "[]")
        if event in subscribed or "*" in subscribed:
            asyncio.create_task(
                _deliver(dict(row), event, payload)
            )


async def _deliver(
    endpoint: dict, event: str, payload: dict, attempt: int = 1
) -> None:
    body = json.dumps({"event": event, "payload": payload}, default=str)
    sig = hmac.new(
        endpoint["secret"].encode(), body.encode(), hashlib.sha256
    ).hexdigest() if endpoint["secret"] else ""

    headers = {
        "Content-Type": "application/json",
        "X-Androbugger-Event": event,
        "X-Androbugger-Signature": f"sha256={sig}",
    }

    response_status: int | None = None
    error: str | None = None
    delivered_at: str | None = None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(endpoint["url"], content=body, headers=headers)
        response_status = resp.status_code
        delivered_at = datetime.now(timezone.utc).isoformat()
        if resp.is_error:
            error = f"HTTP {resp.status_code}"
    except Exception as exc:
        error = str(exc)

    async with get_db() as db:
        await db.execute(
            "INSERT INTO webhook_deliveries"
            " (endpoint_id, event, payload, response_status, delivered_at, error, attempts)"
            " VALUES (?,?,?,?,?,?,?)",
            (endpoint["id"], event, body, response_status, delivered_at, error, attempt),
        )
        await db.commit()

    if error and attempt < settings.webhook_retry_attempts:
        await asyncio.sleep(2 ** attempt)
        await _deliver(endpoint, event, payload, attempt + 1)


async def test_endpoint(endpoint_id: str) -> dict:
    """Send a test payload and return the delivery result."""
    async with get_db() as db:
        row = await (await db.execute(
            "SELECT id, url, secret FROM webhook_endpoints WHERE id=?", (endpoint_id,)
        )).fetchone()

    if not row:
        return {"error": "Endpoint not found"}

    payload = {"event": "test", "timestamp": datetime.now(timezone.utc).isoformat()}
    body = json.dumps(payload)
    sig = hmac.new(
        row["secret"].encode(), body.encode(), hashlib.sha256
    ).hexdigest() if row["secret"] else ""

    headers = {
        "Content-Type": "application/json",
        "X-Androbugger-Event": "test",
        "X-Androbugger-Signature": f"sha256={sig}",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(row["url"], content=body, headers=headers)
        return {"status": resp.status_code, "ok": not resp.is_error}
    except Exception as exc:
        return {"error": str(exc), "ok": False}
