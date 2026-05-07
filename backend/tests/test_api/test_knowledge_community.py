"""Tests for knowledge community contribution endpoints."""
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
        dev_id = str(uuid.uuid4())
        tech_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        async with get_db() as db:
            await db.execute(
                "INSERT INTO users (id, username, password_hash, role, created_at)"
                " VALUES (?,?,?,?,?)",
                (dev_id, "dev", "x", "developer", now),
            )
            await db.execute(
                "INSERT INTO users (id, username, password_hash, role, created_at)"
                " VALUES (?,?,?,?,?)",
                (tech_id, "tech", "x", "technician", now),
            )
            await db.commit()
        dev_token = create_access_token(dev_id, "dev", "developer")
        tech_token = create_access_token(tech_id, "tech", "technician")
        yield {
            "dev_headers": {"Authorization": f"Bearer {dev_token}"},
            "tech_headers": {"Authorization": f"Bearer {tech_token}"},
            "dev_id": dev_id,
            "tech_id": tech_id,
        }
    finally:
        db_module._db_path = original


async def test_create_and_list_entry(setup):
    from androbugger.main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/knowledge/entries", headers=setup["dev_headers"], json={
            "title": "ANR Fix Guide",
            "content": "When you see an ANR, check the main thread stack trace...",
            "namespace": "manual",
        })
        assert resp.status_code == 200
        entry_id = resp.json()["entry"]["id"]

        resp = await c.get("/api/knowledge/entries", headers=setup["tech_headers"])
        assert resp.status_code == 200
        titles = [e["title"] for e in resp.json()["entries"]]
        assert "ANR Fix Guide" in titles


async def test_entry_feedback_vote(setup):
    from androbugger.main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        # Create entry
        resp = await c.post("/api/knowledge/entries", headers=setup["dev_headers"], json={
            "title": "Crash Fix", "content": "Check tombstones for SIGSEGV patterns.", "namespace": "manual",
        })
        entry_id = resp.json()["entry"]["id"]

        # Vote helpful
        resp = await c.post(
            f"/api/knowledge/entries/{entry_id}/feedback?helpful=true",
            headers=setup["tech_headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["helpful_votes"] == 1
        assert resp.json()["unhelpful_votes"] == 0

        # Change vote to unhelpful (upsert)
        resp = await c.post(
            f"/api/knowledge/entries/{entry_id}/feedback?helpful=false",
            headers=setup["tech_headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["helpful_votes"] == 0
        assert resp.json()["unhelpful_votes"] == 1


async def test_update_entry(setup):
    from androbugger.main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/knowledge/entries", headers=setup["dev_headers"], json={
            "title": "Old Title", "content": "Old content here.", "namespace": "manual",
        })
        entry_id = resp.json()["entry"]["id"]

        resp = await c.put(f"/api/knowledge/entries/{entry_id}",
                           headers=setup["dev_headers"],
                           json={"title": "New Title"})
        assert resp.status_code == 200

        resp = await c.get("/api/knowledge/entries", headers=setup["dev_headers"])
        titles = [e["title"] for e in resp.json()["entries"]]
        assert "New Title" in titles
        assert "Old Title" not in titles


async def test_list_with_search(setup):
    from androbugger.main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/api/knowledge/entries", headers=setup["dev_headers"], json={
            "title": "Unique XYZ", "content": "xyz content", "namespace": "manual",
        })
        await c.post("/api/knowledge/entries", headers=setup["dev_headers"], json={
            "title": "Another Entry", "content": "abc content", "namespace": "manual",
        })

        resp = await c.get("/api/knowledge/entries?q=XYZ", headers=setup["tech_headers"])
        assert resp.status_code == 200
        titles = [e["title"] for e in resp.json()["entries"]]
        assert "Unique XYZ" in titles
        assert "Another Entry" not in titles
