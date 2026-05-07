"""Analytics endpoints — diagnostics trends, failure patterns, device health."""
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends

from androbugger.auth.middleware import require_role
from androbugger.db.database import get_db

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/overview")
async def overview(
    user: Annotated[dict, Depends(require_role("developer"))],
):
    """Total sessions, resolved %, avg TTR, top-5 root causes."""
    async with get_db() as db:
        row = await (await db.execute(
            "SELECT COUNT(*) AS total,"
            " SUM(CASE WHEN status='resolved' THEN 1 ELSE 0 END) AS resolved,"
            " AVG(CASE WHEN status='resolved' AND completed_at IS NOT NULL"
            "   THEN (julianday(completed_at) - julianday(started_at)) * 86400"
            "   ELSE NULL END) AS avg_ttr_seconds"
            " FROM diagnostic_sessions"
        )).fetchone()

        top_causes = await (await db.execute(
            "SELECT root_cause, COUNT(*) AS cnt"
            " FROM diagnostic_sessions"
            " WHERE root_cause IS NOT NULL AND root_cause != ''"
            " GROUP BY root_cause ORDER BY cnt DESC LIMIT 5"
        )).fetchall()

    return {
        "total_sessions": row["total"] or 0,
        "resolved_count": row["resolved"] or 0,
        "resolved_pct": round((row["resolved"] or 0) / max(row["total"] or 1, 1) * 100, 1),
        "avg_ttr_seconds": round(row["avg_ttr_seconds"] or 0, 1),
        "top_root_causes": [{"root_cause": r["root_cause"], "count": r["cnt"]} for r in top_causes],
    }


@router.get("/trends")
async def trends(
    user: Annotated[dict, Depends(require_role("developer"))],
    days: int = 30,
):
    """Daily session counts + failure rate for the last N days."""
    async with get_db() as db:
        rows = await (await db.execute(
            "SELECT substr(started_at, 1, 10) AS day,"
            " COUNT(*) AS total,"
            " SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed"
            " FROM diagnostic_sessions"
            " WHERE started_at >= datetime('now', ?)"
            " GROUP BY day ORDER BY day",
            (f"-{days} days",),
        )).fetchall()

    return {
        "days": days,
        "data": [
            {
                "date": r["day"],
                "total": r["total"],
                "failed": r["failed"],
                "fail_rate": round(r["failed"] / max(r["total"], 1) * 100, 1),
            }
            for r in rows
        ],
    }


@router.get("/failure-patterns")
async def failure_patterns(
    user: Annotated[dict, Depends(require_role("developer"))],
    limit: int = 20,
):
    """Top recurring root-cause patterns across all sessions."""
    async with get_db() as db:
        rows = await (await db.execute(
            "SELECT root_cause, COUNT(*) AS cnt,"
            " MIN(id) AS example_session_id,"
            " COUNT(DISTINCT device_serial) AS device_count"
            " FROM diagnostic_sessions"
            " WHERE root_cause IS NOT NULL AND root_cause != ''"
            " GROUP BY root_cause HAVING cnt > 1"
            " ORDER BY cnt DESC LIMIT ?",
            (limit,),
        )).fetchall()

    return {
        "patterns": [
            {
                "root_cause": r["root_cause"],
                "count": r["cnt"],
                "device_count": r["device_count"],
                "example_session_id": r["example_session_id"],
            }
            for r in rows
        ]
    }


@router.get("/device-health/{serial}")
async def device_health(
    serial: str,
    user: Annotated[dict, Depends(require_role("developer"))],
    limit: int = 90,
):
    """Hardware check history for a specific device."""
    async with get_db() as db:
        rows = await (await db.execute(
            "SELECT id, checked_at, overall_status"
            " FROM hardware_checks WHERE device_serial=?"
            " ORDER BY checked_at DESC LIMIT ?",
            (serial, limit),
        )).fetchall()

    return {
        "device_serial": serial,
        "checks": [
            {"id": r["id"], "checked_at": r["checked_at"], "overall_status": r["overall_status"]}
            for r in rows
        ],
    }


@router.get("/regression-map")
async def regression_map(
    user: Annotated[dict, Depends(require_role("developer"))],
    months: int = 6,
):
    """Month × device failure-rate matrix for regression heat-map."""
    async with get_db() as db:
        rows = await (await db.execute(
            "SELECT device_serial,"
            " substr(started_at, 1, 7) AS month,"
            " COUNT(*) AS total,"
            " SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed"
            " FROM diagnostic_sessions"
            " WHERE started_at >= datetime('now', ?)"
            " GROUP BY device_serial, month"
            " ORDER BY device_serial, month",
            (f"-{months} months",),
        )).fetchall()

    # Build matrix: {device_serial: {month: fail_rate}}
    matrix: dict[str, dict[str, float]] = {}
    for r in rows:
        d = matrix.setdefault(r["device_serial"], {})
        d[r["month"]] = round(r["failed"] / max(r["total"], 1) * 100, 1)

    return {"months": months, "matrix": matrix}
