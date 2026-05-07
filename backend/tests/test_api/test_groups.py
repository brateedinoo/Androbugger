"""Tests for device group CRUD endpoints."""
import uuid
import httpx
import pytest


pytestmark = pytest.mark.asyncio


@pytest.fixture
async def db_with_admin(tmp_path):
    """Initialise a fresh DB in a temp dir and return an admin user dict."""
    import androbugger.db.database as db_module
    from datetime import datetime, timezone

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
                (user_id, "admin", "x", "admin", datetime.now(timezone.utc).isoformat()),
            )
            await db.commit()
        yield {"id": user_id, "username": "admin", "role": "admin"}
    finally:
        db_module._db_path = original


@pytest.fixture
async def client(db_with_admin):
    """AsyncClient with a seeded DB and admin auth headers."""
    from androbugger.main import app
    from androbugger.auth.middleware import create_access_token

    token = create_access_token(db_with_admin["id"], "admin", "admin")
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c, headers


async def test_create_and_list_group(client):
    c, headers = client
    # Create
    resp = await c.post("/api/device-groups", json={"name": "Test Group", "color": "#ff0000"}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["group"]["name"] == "Test Group"
    group_id = data["group"]["id"]

    # List
    resp = await c.get("/api/device-groups", headers=headers)
    assert resp.status_code == 200
    names = [g["name"] for g in resp.json()["groups"]]
    assert "Test Group" in names

    # Get detail
    resp = await c.get(f"/api/device-groups/{group_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["group"]["name"] == "Test Group"


async def test_add_and_remove_member(client):
    c, headers = client
    # Create group
    resp = await c.post("/api/device-groups", json={"name": "G2"}, headers=headers)
    group_id = resp.json()["group"]["id"]

    # Add member
    resp = await c.post(
        f"/api/device-groups/{group_id}/members",
        json={"device_serials": ["serial1", "serial2"]},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["added"] == 2

    # Verify
    resp = await c.get(f"/api/device-groups/{group_id}", headers=headers)
    serials = [m["device_serial"] for m in resp.json()["members"]]
    assert "serial1" in serials and "serial2" in serials

    # Remove one
    resp = await c.delete(f"/api/device-groups/{group_id}/members/serial1", headers=headers)
    assert resp.status_code == 200
    resp = await c.get(f"/api/device-groups/{group_id}", headers=headers)
    serials = [m["device_serial"] for m in resp.json()["members"]]
    assert "serial1" not in serials
    assert "serial2" in serials


async def test_delete_group(client):
    c, headers = client
    resp = await c.post("/api/device-groups", json={"name": "ToDelete"}, headers=headers)
    group_id = resp.json()["group"]["id"]

    resp = await c.delete(f"/api/device-groups/{group_id}", headers=headers)
    assert resp.status_code == 200

    resp = await c.get(f"/api/device-groups/{group_id}", headers=headers)
    assert resp.status_code == 404


async def test_update_group(client):
    c, headers = client
    resp = await c.post("/api/device-groups", json={"name": "Original"}, headers=headers)
    group_id = resp.json()["group"]["id"]

    resp = await c.put(f"/api/device-groups/{group_id}", json={"name": "Updated", "color": "#00ff00"}, headers=headers)
    assert resp.status_code == 200

    resp = await c.get(f"/api/device-groups/{group_id}", headers=headers)
    assert resp.json()["group"]["name"] == "Updated"
