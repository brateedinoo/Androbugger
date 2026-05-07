"""Admin REST endpoints: users, audit log, system stats."""
import csv
import io
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from androbugger.auth.middleware import require_role
from androbugger.auth.users import create_user
from androbugger.config import settings
from androbugger.db.database import get_db

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ── Stats ──────────────────────────────────────────────────────────────────────

@router.get("/stats")
async def admin_stats(user: Annotated[dict, Depends(require_role("admin"))]):
    async with get_db() as db:
        users_row = await (await db.execute("SELECT COUNT(*) FROM users")).fetchone()
        sessions_row = await (await db.execute("SELECT COUNT(*) FROM diagnostic_sessions")).fetchone()
        resolved_row = await (await db.execute(
            "SELECT COUNT(*) FROM diagnostic_sessions WHERE status='resolved'"
        )).fetchone()
        audit_row = await (await db.execute("SELECT COUNT(*) FROM audit_log")).fetchone()
        recent_rows = await (await db.execute(
            """SELECT DATE(timestamp) as day, COUNT(*) as count
               FROM audit_log
               WHERE timestamp >= ?
               GROUP BY day ORDER BY day""",
            ((datetime.now(UTC) - timedelta(days=7)).isoformat(),),
        )).fetchall()
        providers_row = await (await db.execute(
            "SELECT name, type, enabled FROM llm_providers"
        )).fetchall()

    return {
        "user_count": users_row[0],
        "session_count": sessions_row[0],
        "resolved_count": resolved_row[0],
        "audit_entry_count": audit_row[0],
        "activity_7d": [dict(r) for r in recent_rows],
        "llm_providers": [dict(r) for r in providers_row],
    }


# ── Users ──────────────────────────────────────────────────────────────────────

class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "technician"


class UpdateRoleRequest(BaseModel):
    role: str


_VALID_ROLES = {"technician", "qa_engineer", "developer", "admin"}


@router.get("/users")
async def list_users(user: Annotated[dict, Depends(require_role("admin"))]):
    async with get_db() as db:
        rows = await (await db.execute(
            "SELECT id, username, role, created_at, last_login, force_password_change FROM users ORDER BY created_at"
        )).fetchall()
    return {"users": [dict(r) for r in rows]}


@router.post("/users")
async def admin_create_user(
    body: CreateUserRequest,
    user: Annotated[dict, Depends(require_role("admin"))],
):
    if body.role not in _VALID_ROLES:
        raise HTTPException(status_code=422, detail=f"Invalid role: {body.role}")
    try:
        new_user = await create_user(body.username, body.password, body.role)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"user": new_user}


@router.patch("/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    body: UpdateRoleRequest,
    user: Annotated[dict, Depends(require_role("admin"))],
):
    if body.role not in _VALID_ROLES:
        raise HTTPException(status_code=422, detail=f"Invalid role: {body.role}")
    if user_id == user["id"]:
        raise HTTPException(status_code=400, detail="Cannot change your own role")
    async with get_db() as db:
        result = await db.execute("UPDATE users SET role=? WHERE id=?", (body.role, user_id))
        await db.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    user: Annotated[dict, Depends(require_role("admin"))],
):
    if user_id == user["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    async with get_db() as db:
        result = await db.execute("DELETE FROM users WHERE id=?", (user_id,))
        await db.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}


# ── Audit log ──────────────────────────────────────────────────────────────────

@router.get("/audit")
async def list_audit(
    user: Annotated[dict, Depends(require_role("admin"))],
    action: str | None = None,
    severity: str | None = None,
    user_id: str | None = None,
    device_serial: str | None = None,
    days: int = 30,
    page: int = 1,
    per_page: int = 50,
):
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    conditions = ["timestamp >= ?"]
    params: list = [cutoff]
    if action:
        conditions.append("action LIKE ?")
        params.append(f"%{action}%")
    if severity:
        conditions.append("severity=?")
        params.append(severity)
    if user_id:
        conditions.append("user_id=?")
        params.append(user_id)
    if device_serial:
        conditions.append("device_serial=?")
        params.append(device_serial)

    where = "WHERE " + " AND ".join(conditions)
    offset = (page - 1) * per_page

    async with get_db() as db:
        total_row = await (await db.execute(f"SELECT COUNT(*) FROM audit_log {where}", params)).fetchone()
        rows = await (await db.execute(
            f"SELECT * FROM audit_log {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            params + [per_page, offset],
        )).fetchall()

    return {
        "entries": [dict(r) for r in rows],
        "total": total_row[0],
        "page": page,
        "per_page": per_page,
    }


@router.get("/audit/export")
async def export_audit_csv(
    user: Annotated[dict, Depends(require_role("admin"))],
    days: int = 30,
):
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    async with get_db() as db:
        rows = await (await db.execute(
            "SELECT * FROM audit_log WHERE timestamp >= ? ORDER BY timestamp DESC",
            (cutoff,),
        )).fetchall()

    buf = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))

    return Response(
        content=buf.getvalue().encode(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="audit-{days}d.csv"'},
    )


@router.delete("/audit/prune")
async def prune_audit(user: Annotated[dict, Depends(require_role("admin"))]):
    """Delete audit entries older than the configured retention period."""
    cutoff = (datetime.now(UTC) - timedelta(days=settings.audit_retention_days)).isoformat()
    async with get_db() as db:
        result = await db.execute("DELETE FROM audit_log WHERE timestamp < ?", (cutoff,))
        await db.commit()
    return {"deleted": result.rowcount}


# ── LLM providers ──────────────────────────────────────────────────────────────

class UpdateProviderRequest(BaseModel):
    enabled: bool


@router.get("/llm-providers")
async def list_llm_providers(user: Annotated[dict, Depends(require_role("admin"))]):
    async with get_db() as db:
        rows = await (await db.execute("SELECT * FROM llm_providers")).fetchall()
    return {"providers": [dict(r) for r in rows]}


@router.patch("/llm-providers/{provider_id}")
async def update_llm_provider(
    provider_id: str,
    body: UpdateProviderRequest,
    user: Annotated[dict, Depends(require_role("admin"))],
):
    async with get_db() as db:
        result = await db.execute(
            "UPDATE llm_providers SET enabled=? WHERE id=?", (body.enabled, provider_id)
        )
        await db.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Provider not found")
    return {"ok": True}


# ── Fine-tuning ────────────────────────────────────────────────────────────────

@router.get("/finetune/stats")
async def finetune_stats(user: Annotated[dict, Depends(require_role("admin"))]):
    from androbugger.llm.finetune import get_finetune_stats
    return await get_finetune_stats()


class FinetuneExportRequest(BaseModel):
    output_path: str = "/tmp/androbugger-training.jsonl"
    min_quality: float = 0.0


@router.post("/finetune/export")
async def finetune_export(
    body: FinetuneExportRequest,
    user: Annotated[dict, Depends(require_role("admin"))],
):
    from androbugger.llm.finetune import export_training_data_for_user
    result = export_training_data_for_user(
        body.output_path,
        user_id=user["id"],
        min_quality=body.min_quality,
    )
    return {
        "record_count": result.record_count,
        "skipped_count": result.skipped_count,
        "path": result.path,
    }
