"""arq-compatible worker functions for scheduled diagnostics and regression detection."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

# Severity ordering for regression detection
_SEVERITY_ORDER = {"unknown": 0, "pass": 1, "info": 1, "warning": 2, "critical": 3}


async def run_scheduled_diagnostic(ctx: dict, schedule_id: str) -> None:
    """Run a scheduled diagnostic for a single device or all members of a group."""
    from androbugger.api.notifications import create_notification
    from androbugger.db.database import get_db

    async with get_db() as db:
        row = await (await db.execute(
            "SELECT * FROM scheduled_diagnostics WHERE id=? AND enabled=TRUE",
            (schedule_id,),
        )).fetchone()

    if not row:
        logger.warning("Schedule %s not found or disabled", schedule_id)
        return

    schedule = dict(row)
    now = datetime.now(UTC).isoformat()

    # Collect target serials
    serials: list[str] = []
    if schedule.get("device_serial"):
        serials = [schedule["device_serial"]]
    elif schedule.get("group_id"):
        async with get_db() as db:
            members = await (await db.execute(
                "SELECT device_serial FROM device_group_members WHERE group_id=?",
                (schedule["group_id"],),
            )).fetchall()
        serials = [m["device_serial"] for m in members]

    if not serials:
        logger.warning("Schedule %s has no target serials", schedule_id)
        return

    session_ids: list[str] = []
    for serial in serials:
        try:
            session_id = await _start_scheduled_session(
                serial=serial,
                user_id=schedule["created_by"],
                template_id=schedule.get("template_id"),
            )
            session_ids.append(session_id)
        except Exception as exc:
            logger.error("Scheduled diagnostic failed for %s: %s", serial, exc)

    # Update schedule tracking
    async with get_db() as db:
        await db.execute(
            "UPDATE scheduled_diagnostics SET last_run_at=?, last_session_id=? WHERE id=?",
            (now, session_ids[-1] if session_ids else None, schedule_id),
        )
        await db.commit()

    # Create notification
    await create_notification(
        kind="scheduled_run",
        title=f"Scheduled diagnostic ran: {schedule['name']}",
        body=f"Started {len(session_ids)} session(s) for {len(serials)} device(s).",
        user_id=schedule["created_by"],
    )


async def _start_scheduled_session(serial: str, user_id: str, template_id: str | None) -> str:
    """Insert a session row and fire the diagnosis background task."""
    import uuid
    from datetime import datetime

    from androbugger.db.database import get_db

    session_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    async with get_db() as db:
        await db.execute(
            """INSERT INTO diagnostic_sessions (id, device_serial, user_id, status, started_at)
               VALUES (?, ?, ?, 'running', ?)""",
            (session_id, serial, user_id, now),
        )
        await db.commit()

    try:
        import asyncio

        from androbugger.api.diagnostics import _run_diagnosis
        asyncio.create_task(_run_diagnosis(session_id, serial, template_id or "default"))
    except Exception as exc:
        logger.error("Failed to start diagnosis task: %s", exc)

    return session_id


async def check_regression(ctx: dict, session_id: str) -> None:
    """Compare new session severity against last 5 for this device; notify if escalated."""
    from androbugger.api.notifications import create_notification
    from androbugger.db.database import get_db

    async with get_db() as db:
        current = await (await db.execute(
            "SELECT device_serial, deterministic_summary, user_id FROM diagnostic_sessions WHERE id=?",
            (session_id,),
        )).fetchone()

    if not current:
        return

    serial = current["device_serial"]
    try:
        import json
        summary = json.loads(current["deterministic_summary"] or "{}")
        new_severity = summary.get("severity", "unknown")
    except Exception:
        new_severity = "unknown"

    async with get_db() as db:
        past_rows = await (await db.execute(
            """SELECT deterministic_summary FROM diagnostic_sessions
               WHERE device_serial=? AND id != ? AND status IN ('completed','resolved')
               ORDER BY started_at DESC LIMIT 5""",
            (serial, session_id),
        )).fetchall()

    if not past_rows:
        return  # No history to compare

    past_severities = []
    for row in past_rows:
        try:
            import json
            s = json.loads(row["deterministic_summary"] or "{}")
            past_severities.append(s.get("severity", "unknown"))
        except Exception:
            pass

    if not past_severities:
        return

    avg_past_score = sum(_SEVERITY_ORDER.get(s, 0) for s in past_severities) / len(past_severities)
    new_score = _SEVERITY_ORDER.get(new_severity, 0)

    if new_score > avg_past_score + 0.5:
        await create_notification(
            kind="regression_detected",
            title=f"Regression detected on {serial}",
            body=f"Session severity '{new_severity}' is higher than recent average for this device.",
            session_id=session_id,
            device_serial=serial,
        )
        logger.info("Regression detected for session %s on %s", session_id, serial)
