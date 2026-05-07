"""Scheduled diagnostics CRUD — create/list/delete cron-based diagnostic jobs."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from androbugger.auth.middleware import get_current_user, require_role
from androbugger.db.database import get_db

router = APIRouter(prefix="/api/scheduled-diagnostics", tags=["scheduled"])


def _next_run(cron_expr: str) -> str | None:
    try:
        from croniter import croniter
        now = datetime.now(timezone.utc)
        c = croniter(cron_expr, now)
        return c.get_next(datetime).isoformat()
    except Exception:
        return None


class CreateScheduleRequest(BaseModel):
    name: str
    cron_expr: str
    device_serial: str | None = None
    group_id: str | None = None
    template_id: str | None = None
    enabled: bool = True


@router.get("")
async def list_schedules(user: Annotated[dict, Depends(get_current_user)]):
    async with get_db() as db:
        rows = await (await db.execute(
            "SELECT * FROM scheduled_diagnostics ORDER BY created_at DESC"
        )).fetchall()
    return {"schedules": [dict(r) for r in rows]}


@router.post("")
async def create_schedule(
    body: CreateScheduleRequest,
    user: Annotated[dict, Depends(require_role("admin"))],
):
    if not body.device_serial and not body.group_id:
        raise HTTPException(status_code=422, detail="Provide device_serial or group_id")

    # Validate cron expression
    next_run = _next_run(body.cron_expr)
    if next_run is None:
        raise HTTPException(status_code=422, detail=f"Invalid cron expression: {body.cron_expr}")

    schedule_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with get_db() as db:
        await db.execute(
            """INSERT INTO scheduled_diagnostics
               (id, name, device_serial, group_id, cron_expr, enabled, template_id,
                created_by, created_at, next_run_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (schedule_id, body.name, body.device_serial, body.group_id,
             body.cron_expr, body.enabled, body.template_id,
             user["id"], now, next_run),
        )
        await db.commit()

    return {"schedule": {"id": schedule_id, "name": body.name, "next_run_at": next_run}}


@router.patch("/{schedule_id}/toggle")
async def toggle_schedule(
    schedule_id: str,
    user: Annotated[dict, Depends(require_role("admin"))],
):
    async with get_db() as db:
        row = await (await db.execute(
            "SELECT enabled FROM scheduled_diagnostics WHERE id=?", (schedule_id,)
        )).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Schedule not found")
        new_state = not row["enabled"]
        await db.execute(
            "UPDATE scheduled_diagnostics SET enabled=? WHERE id=?", (new_state, schedule_id)
        )
        await db.commit()
    return {"ok": True, "enabled": new_state}


@router.delete("/{schedule_id}")
async def delete_schedule(
    schedule_id: str,
    user: Annotated[dict, Depends(require_role("admin"))],
):
    async with get_db() as db:
        result = await db.execute(
            "DELETE FROM scheduled_diagnostics WHERE id=?", (schedule_id,)
        )
        await db.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Schedule not found")
    return {"ok": True}
