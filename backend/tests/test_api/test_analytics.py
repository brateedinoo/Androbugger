"""Tests for analytics REST endpoints."""
import uuid
import httpx
import pytest
from datetime import datetime, timezone

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def setup(tmp_path):
    import androbugger.db.database as db_module
    from androbugger.auth.middleware import create_access_token
    from androbugger.db.database import init_db, get_db

    db_file = tmp_path / "test.db"
    original = db_module._db_path
    db_module._db_path = str(db_file)
    try:
        await init_db()
        user_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        async with get_db() as db:
            await db.execute(
                "INSERT INTO users (id, username, password_hash, role, created_at)"
                " VALUES (?,?,?,?,?)",
                (user_id, "dev", "x", "developer", now),
            )
            # Seed two sessions: one resolved, one failed
            sess1 = str(uuid.uuid4())
            sess2 = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO diagnostic_sessions"
                " (id, device_serial, user_id, status, started_at, completed_at, root_cause)"
                " VALUES (?,?,?,?,?,?,?)",
                (sess1, "SN001", user_id, "resolved", now, now, "OOM in com.app"),
            )
            await db.execute(
                "INSERT INTO diagnostic_sessions"
                " (id, device_serial, user_id, status, started_at)"
                " VALUES (?,?,?,?,?)",
                (sess2, "SN001", user_id, "failed", now),
            )
            await db.commit()
        token = create_access_token(user_id, "dev", "developer")
        yield {"headers": {"Authorization": f"Bearer {token}"}, "user_id": user_id}
    finally:
        db_module._db_path = original


async def test_overview(setup):
    from androbugger.main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/analytics/overview", headers=setup["headers"])
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_sessions"] == 2
    assert data["resolved_count"] == 1
    assert data["resolved_pct"] == 50.0


async def test_trends(setup):
    from androbugger.main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/analytics/trends?days=30", headers=setup["headers"])
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    # Both sessions are today, so there should be at least one entry
    assert len(data["data"]) >= 1
    total = sum(d["total"] for d in data["data"])
    assert total == 2


async def test_failure_patterns(setup):
    from androbugger.main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/analytics/failure-patterns", headers=setup["headers"])
    assert resp.status_code == 200
    # Only one root_cause entry so patterns need count>1, expect empty
    assert resp.json()["patterns"] == []


async def test_device_health(setup):
    from androbugger.main import app
    from androbugger.db.database import get_db
    import androbugger.db.database as db_module
    # Insert a hardware check
    now = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        await db.execute(
            "INSERT INTO hardware_checks (id, device_serial, checked_at, overall_status, results_json)"
            " VALUES (?,?,?,?,?)",
            (str(uuid.uuid4()), "SN001", now, "pass", "{}"),
        )
        await db.commit()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/analytics/device-health/SN001", headers=setup["headers"])
    assert resp.status_code == 200
    assert len(resp.json()["checks"]) == 1
    assert resp.json()["checks"][0]["overall_status"] == "pass"


async def test_regression_map(setup):
    from androbugger.main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/analytics/regression-map", headers=setup["headers"])
    assert resp.status_code == 200
    assert "matrix" in resp.json()
