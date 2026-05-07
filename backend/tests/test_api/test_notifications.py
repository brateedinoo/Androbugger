"""Tests for notification REST endpoints and the create_notification helper."""
import uuid
import httpx
import pytest


pytestmark = pytest.mark.asyncio


@pytest.fixture
async def setup(tmp_path):
    """Initialise a fresh DB and return (user_id, auth_headers)."""
    import androbugger.db.database as db_module
    from datetime import datetime, timezone
    from androbugger.auth.middleware import create_access_token

    db_file = tmp_path / "test.db"
    original = db_module._db_path
    db_module._db_path = str(db_file)
    try:
        from androbugger.db.database import init_db, get_db
        await init_db()
        user_id = str(uuid.uuid4())
        async with get_db() as db:
            await db.execute(
                "INSERT INTO users (id, username, password_hash, role, created_at) VALUES (?,?,?,?,?)",
                (user_id, "testuser", "x", "technician", datetime.now(timezone.utc).isoformat()),
            )
            await db.commit()
        token = create_access_token(user_id, "testuser", "technician")
        yield user_id, {"Authorization": f"Bearer {token}"}
    finally:
        db_module._db_path = original


async def test_create_and_list_notifications(setup):
    from androbugger.main import app
    from androbugger.api.notifications import create_notification

    user_id, headers = setup
    await create_notification("session_complete", "Session done", user_id=user_id)
    await create_notification("plugin_error", "Broadcast alert", user_id=None)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/notifications", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["unread_count"] >= 2
        titles = [n["title"] for n in data["notifications"]]
        assert "Session done" in titles
        assert "Broadcast alert" in titles


async def test_mark_notification_read(setup):
    from androbugger.main import app
    from androbugger.api.notifications import create_notification

    user_id, headers = setup
    notif_id = await create_notification("session_complete", "To read", user_id=user_id)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(f"/api/notifications/{notif_id}/read", headers=headers)
        assert resp.status_code == 200

        resp = await c.get("/api/notifications?unread_only=true", headers=headers)
        ids = [n["id"] for n in resp.json()["notifications"]]
        assert notif_id not in ids


async def test_mark_all_read(setup):
    from androbugger.main import app
    from androbugger.api.notifications import create_notification

    user_id, headers = setup
    await create_notification("session_failed", "Fail 1", user_id=user_id)
    await create_notification("session_failed", "Fail 2", user_id=user_id)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/notifications/read-all", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["updated"] >= 2

        resp = await c.get("/api/notifications?unread_only=true", headers=headers)
        assert resp.json()["unread_count"] == 0


async def test_delete_notification(setup):
    from androbugger.main import app
    from androbugger.api.notifications import create_notification

    user_id, headers = setup
    notif_id = await create_notification("hardware_alert", "Alert", user_id=user_id)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete(f"/api/notifications/{notif_id}", headers=headers)
        assert resp.status_code == 200

        resp = await c.get("/api/notifications", headers=headers)
        ids = [n["id"] for n in resp.json()["notifications"]]
        assert notif_id not in ids
