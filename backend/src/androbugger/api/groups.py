"""Device group CRUD endpoints."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from androbugger.auth.middleware import require_role
from androbugger.db.database import get_db

router = APIRouter(prefix="/api/device-groups", tags=["groups"])


class CreateGroupRequest(BaseModel):
    name: str
    description: str | None = None
    color: str | None = None


class UpdateGroupRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    color: str | None = None


class AddMembersRequest(BaseModel):
    device_serials: list[str]


@router.get("")
async def list_groups(user: Annotated[dict, Depends(require_role("technician"))]):
    async with get_db() as db:
        rows = await (await db.execute(
            "SELECT g.*, COUNT(m.device_serial) AS member_count FROM device_groups g "
            "LEFT JOIN device_group_members m ON g.id = m.group_id "
            "GROUP BY g.id ORDER BY g.created_at"
        )).fetchall()
    return {"groups": [dict(r) for r in rows]}


@router.post("")
async def create_group(
    body: CreateGroupRequest,
    user: Annotated[dict, Depends(require_role("developer"))],
):
    group_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    try:
        async with get_db() as db:
            await db.execute(
                "INSERT INTO device_groups (id, name, description, color, created_by, created_at) VALUES (?,?,?,?,?,?)",
                (group_id, body.name, body.description, body.color, user["id"], now),
            )
            await db.commit()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"group": {"id": group_id, "name": body.name, "description": body.description, "color": body.color}}


@router.get("/{group_id}")
async def get_group(group_id: str, user: Annotated[dict, Depends(require_role("technician"))]):
    async with get_db() as db:
        group = await (await db.execute(
            "SELECT * FROM device_groups WHERE id=?", (group_id,)
        )).fetchone()
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
        members = await (await db.execute(
            "SELECT device_serial, added_at FROM device_group_members WHERE group_id=?", (group_id,)
        )).fetchall()
    return {"group": dict(group), "members": [dict(m) for m in members]}


@router.put("/{group_id}")
async def update_group(
    group_id: str,
    body: UpdateGroupRequest,
    user: Annotated[dict, Depends(require_role("developer"))],
):
    updates: list[str] = []
    params: list = []
    if body.name is not None:
        updates.append("name=?")
        params.append(body.name)
    if body.description is not None:
        updates.append("description=?")
        params.append(body.description)
    if body.color is not None:
        updates.append("color=?")
        params.append(body.color)
    if not updates:
        raise HTTPException(status_code=422, detail="No fields to update")
    params.append(group_id)
    async with get_db() as db:
        result = await db.execute(f"UPDATE device_groups SET {', '.join(updates)} WHERE id=?", params)
        await db.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Group not found")
    return {"ok": True}


@router.delete("/{group_id}")
async def delete_group(group_id: str, user: Annotated[dict, Depends(require_role("developer"))]):
    async with get_db() as db:
        result = await db.execute("DELETE FROM device_groups WHERE id=?", (group_id,))
        await db.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Group not found")
    return {"ok": True}


@router.post("/{group_id}/members")
async def add_members(
    group_id: str,
    body: AddMembersRequest,
    user: Annotated[dict, Depends(require_role("developer"))],
):
    now = datetime.now(UTC).isoformat()
    async with get_db() as db:
        # Verify group exists
        row = await (await db.execute("SELECT id FROM device_groups WHERE id=?", (group_id,))).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Group not found")
        for serial in body.device_serials:
            await db.execute(
                "INSERT OR IGNORE INTO device_group_members (group_id, device_serial, added_at) VALUES (?,?,?)",
                (group_id, serial, now),
            )
        await db.commit()
    return {"ok": True, "added": len(body.device_serials)}


@router.delete("/{group_id}/members/{serial}")
async def remove_member(
    group_id: str,
    serial: str,
    user: Annotated[dict, Depends(require_role("developer"))],
):
    async with get_db() as db:
        result = await db.execute(
            "DELETE FROM device_group_members WHERE group_id=? AND device_serial=?",
            (group_id, serial),
        )
        await db.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Member not found in group")
    return {"ok": True}
