"""Tests for webhook endpoint CRUD."""
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
                (user_id, "admin", "x", "admin", now),
            )
            await db.commit()
        token = create_access_token(user_id, "admin", "admin")
        yield {"headers": {"Authorization": f"Bearer {token}"}, "user_id": user_id}
    finally:
        db_module._db_path = original


async def test_create_and_list_webhooks(setup):
    from androbugger.main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        # Create
        resp = await c.post("/api/webhooks", headers=setup["headers"], json={
            "name": "My Hook",
            "url": "https://example.com/hook",
            "events": ["session.completed"],
        })
        assert resp.status_code == 200
        wid = resp.json()["webhook"]["id"]

        # List
        resp = await c.get("/api/webhooks", headers=setup["headers"])
        assert resp.status_code == 200
        names = [w["name"] for w in resp.json()["webhooks"]]
        assert "My Hook" in names

        # Get single
        resp = await c.get(f"/api/webhooks/{wid}", headers=setup["headers"])
        assert resp.status_code == 200
        assert resp.json()["webhook"]["name"] == "My Hook"


async def test_update_webhook(setup):
    from androbugger.main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/webhooks", headers=setup["headers"], json={
            "name": "Hook", "url": "https://example.com/hook"
        })
        wid = resp.json()["webhook"]["id"]

        resp = await c.put(f"/api/webhooks/{wid}", headers=setup["headers"],
                           json={"enabled": False})
        assert resp.status_code == 200

        resp = await c.get(f"/api/webhooks/{wid}", headers=setup["headers"])
        assert resp.json()["webhook"]["enabled"] == 0  # SQLite bool → int


async def test_delete_webhook(setup):
    from androbugger.main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/webhooks", headers=setup["headers"], json={
            "name": "ToDelete", "url": "https://example.com/hook"
        })
        wid = resp.json()["webhook"]["id"]

        resp = await c.delete(f"/api/webhooks/{wid}", headers=setup["headers"])
        assert resp.status_code == 200

        resp = await c.get(f"/api/webhooks/{wid}", headers=setup["headers"])
        assert resp.status_code == 404


async def test_invalid_event(setup):
    from androbugger.main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/webhooks", headers=setup["headers"], json={
            "name": "Bad", "url": "https://example.com", "events": ["bogus.event"]
        })
        assert resp.status_code == 400
