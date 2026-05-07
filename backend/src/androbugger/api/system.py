"""System health and data-retention management endpoints."""
import os
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from androbugger.auth.middleware import require_role
from androbugger.config import settings
from androbugger.db.database import get_db

router = APIRouter(prefix="/api/system", tags=["system"])

_DEFAULT_RETENTION: dict[str, int] = {
    "diagnostic_sessions": 365,
    "audit_log": 180,
    "webhook_deliveries": 30,
    "notifications": 90,
}

# Column used for age comparison per entity
_ENTITY_TS_COL: dict[str, str] = {
    "diagnostic_sessions": "started_at",
    "audit_log": "timestamp",
    "webhook_deliveries": "delivered_at",
    "notifications": "created_at",
}


@router.get("/health")
async def health(user: Annotated[dict, Depends(require_role("admin"))]):
    """Return system health metrics."""
    db_size = 0
    try:
        db_size = os.path.getsize(str(settings.db_path))
    except OSError:
        pass

    async with get_db() as db:
        session_count = (await (await db.execute(
            "SELECT COUNT(*) FROM diagnostic_sessions"
        )).fetchone())[0]
        knowledge_count = (await (await db.execute(
            "SELECT COUNT(*) FROM knowledge_entries"
        )).fetchone())[0]
        sched_count = (await (await db.execute(
            "SELECT COUNT(*) FROM scheduled_diagnostics WHERE enabled=TRUE"
        )).fetchone())[0]
        next_run_row = await (await db.execute(
            "SELECT MIN(next_run_at) FROM scheduled_diagnostics WHERE enabled=TRUE AND next_run_at IS NOT NULL"
        )).fetchone()

    return {
        "db_size_bytes": db_size,
        "session_count": session_count,
        "knowledge_entry_count": knowledge_count,
        "active_scheduled_count": sched_count,
        "next_scheduled_run": next_run_row[0] if next_run_row else None,
    }


@router.get("/retention")
async def list_retention(user: Annotated[dict, Depends(require_role("admin"))]):
    async with get_db() as db:
        rows = await (await db.execute(
            "SELECT entity, max_age_days, enabled FROM retention_policies"
        )).fetchall()

    db_policies = {r["entity"]: dict(r) for r in rows}
    result = []
    for entity, default_days in _DEFAULT_RETENTION.items():
        if entity in db_policies:
            result.append(db_policies[entity])
        else:
            result.append({"entity": entity, "max_age_days": default_days, "enabled": True})
    return {"policies": result}


class RetentionUpdate(BaseModel):
    max_age_days: int
    enabled: bool = True


@router.put("/retention/{entity}")
async def update_retention(
    entity: str,
    body: RetentionUpdate,
    user: Annotated[dict, Depends(require_role("admin"))],
):
    if entity not in _DEFAULT_RETENTION:
        raise HTTPException(400, f"Unknown entity '{entity}'")
    if body.max_age_days < 1:
        raise HTTPException(400, "max_age_days must be >= 1")

    now = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        await db.execute(
            "INSERT INTO retention_policies (entity, max_age_days, enabled, updated_by, updated_at)"
            " VALUES (?,?,?,?,?)"
            " ON CONFLICT(entity) DO UPDATE SET max_age_days=excluded.max_age_days,"
            "   enabled=excluded.enabled, updated_by=excluded.updated_by, updated_at=excluded.updated_at",
            (entity, body.max_age_days, body.enabled, user["id"], now),
        )
        await db.commit()
    return {"ok": True}


@router.post("/retention/run")
async def run_retention(user: Annotated[dict, Depends(require_role("admin"))]):
    """Execute purge for all enabled retention policies. Returns rows deleted."""
    async with get_db() as db:
        rows = await (await db.execute(
            "SELECT entity, max_age_days, enabled FROM retention_policies WHERE enabled=TRUE"
        )).fetchall()
        policies = {r["entity"]: r["max_age_days"] for r in rows}

    # Fill in defaults for any entity not yet in DB
    for entity, default_days in _DEFAULT_RETENTION.items():
        if entity not in policies:
            policies[entity] = default_days

    deleted: dict[str, int] = {}
    async with get_db() as db:
        for entity, max_days in policies.items():
            ts_col = _ENTITY_TS_COL[entity]
            assert entity in _ENTITY_TS_COL
            assert ts_col in {"started_at", "timestamp", "delivered_at", "created_at"}
            cursor = await db.execute(
                f"DELETE FROM {entity} WHERE {ts_col} < datetime('now', ?)",
                (f"-{max_days} days",),
            )
            deleted[entity] = cursor.rowcount
        await db.commit()

    return {"deleted": deleted}
