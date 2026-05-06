"""Append-only audit log helper."""
import json
from datetime import datetime, timezone

import aiosqlite

from androbugger.db.database import get_db


async def log(
    action: str,
    severity: str = "info",
    user_id: str | None = None,
    device_serial: str | None = None,
    detail: dict | None = None,
    ip_address: str | None = None,
) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        await db.execute(
            """INSERT INTO audit_log (timestamp, user_id, action, severity, device_serial, detail, ip_address)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (ts, user_id, action, severity, device_serial, json.dumps(detail) if detail else None, ip_address),
        )
        await db.commit()
