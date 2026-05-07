"""Knowledge base REST endpoints — search, stats, and community contributions."""
import hashlib
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from androbugger.auth.middleware import get_current_user, require_role
from androbugger.db.database import get_db
from androbugger.knowledge.indexer import index_document, search_knowledge
from androbugger.knowledge.store import get_store

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


class SearchRequest(BaseModel):
    query: str
    namespace: str | None = None
    device_model: str | None = None
    firmware_version: str | None = None
    top_k: int = 8


class EntryCreate(BaseModel):
    title: str
    content: str
    namespace: str = "manual"


class EntryUpdate(BaseModel):
    title: str | None = None
    content: str | None = None


@router.get("/stats")
async def stats(user: Annotated[dict, Depends(get_current_user)]):
    return get_store().get_stats()


@router.post("/search")
async def search(body: SearchRequest, user: Annotated[dict, Depends(get_current_user)]):
    results = search_knowledge(
        query=body.query,
        device_model=body.device_model,
        namespace=body.namespace,
        top_k=body.top_k,
    )
    return {"results": results}


# ── Community contribution endpoints ──────────────────────────────────────────

@router.get("/entries")
async def list_entries(
    user: Annotated[dict, Depends(require_role("technician"))],
    namespace: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    offset = (page - 1) * page_size
    async with get_db() as db:
        params: list = []
        where = ["1=1"]
        if namespace:
            where.append("namespace=?")
            params.append(namespace)
        if q:
            where.append("(title LIKE ? OR metadata LIKE ?)")
            params.extend([f"%{q}%", f"%{q}%"])
        where_sql = " AND ".join(where)

        rows = await (await db.execute(
            f"SELECT id, namespace, title, source, indexed_at, updated_at,"
            f" helpful_votes, unhelpful_votes, author_id, is_manual"
            f" FROM knowledge_entries WHERE {where_sql}"
            f" ORDER BY indexed_at DESC LIMIT ? OFFSET ?",
            params + [page_size, offset],
        )).fetchall()

        total_row = await (await db.execute(
            f"SELECT COUNT(*) FROM knowledge_entries WHERE {where_sql}", params
        )).fetchone()

    return {
        "entries": [dict(r) for r in rows],
        "total": total_row[0],
        "page": page,
        "page_size": page_size,
    }


@router.post("/entries")
async def create_entry(
    body: EntryCreate,
    user: Annotated[dict, Depends(require_role("developer"))],
):
    if body.namespace not in ("manual", "vendor_docs", "aosp_reference"):
        raise HTTPException(400, "namespace must be manual, vendor_docs, or aosp_reference")
    if not body.title.strip() or not body.content.strip():
        raise HTTPException(400, "title and content must not be empty")

    content_hash = hashlib.sha256(body.content.encode()).hexdigest()
    entry_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # Write to a temp file for index_document
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(body.content)
        tmp_path = Path(f.name)

    try:
        index_document(tmp_path, body.title, body.namespace)
    except Exception:
        pass
    finally:
        tmp_path.unlink(missing_ok=True)

    async with get_db() as db:
        await db.execute(
            "INSERT INTO knowledge_entries"
            " (id, namespace, title, content_hash, indexed_at, updated_at,"
            "  helpful_votes, unhelpful_votes, author_id, is_manual, metadata)"
            " VALUES (?,?,?,?,?,?,0,0,?,TRUE,?)",
            (entry_id, body.namespace, body.title, content_hash, now, now,
             user["id"], body.content[:2000]),
        )
        await db.commit()

    return {"entry": {"id": entry_id, "title": body.title, "namespace": body.namespace}}


@router.put("/entries/{entry_id}")
async def update_entry(
    entry_id: str,
    body: EntryUpdate,
    user: Annotated[dict, Depends(require_role("developer"))],
):
    async with get_db() as db:
        row = await (await db.execute(
            "SELECT id, author_id, is_manual FROM knowledge_entries WHERE id=?", (entry_id,)
        )).fetchone()
        if not row:
            raise HTTPException(404, "Entry not found")
        if user["role"] != "admin" and row["author_id"] != user["id"]:
            raise HTTPException(403, "Cannot edit another user's entry")

        now = datetime.now(timezone.utc).isoformat()
        if body.title is not None:
            await db.execute(
                "UPDATE knowledge_entries SET title=?, updated_at=? WHERE id=?",
                (body.title, now, entry_id),
            )
        if body.content is not None:
            content_hash = hashlib.sha256(body.content.encode()).hexdigest()
            # Re-index in background (best-effort)
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
                f.write(body.content)
                tmp_path = Path(f.name)
            try:
                existing = await (await db.execute(
                    "SELECT title FROM knowledge_entries WHERE id=?", (entry_id,)
                )).fetchone()
                index_document(tmp_path, existing["title"], "manual")
            except Exception:
                pass
            finally:
                tmp_path.unlink(missing_ok=True)

            await db.execute(
                "UPDATE knowledge_entries SET content_hash=?, metadata=?, updated_at=? WHERE id=?",
                (content_hash, body.content[:2000], now, entry_id),
            )
        await db.commit()
    return {"ok": True}


@router.delete("/entries/{entry_id}")
async def delete_entry(
    entry_id: str,
    user: Annotated[dict, Depends(require_role("admin"))],
):
    async with get_db() as db:
        await db.execute("DELETE FROM knowledge_entries WHERE id=?", (entry_id,))
        await db.commit()
    return {"ok": True}


@router.post("/entries/{entry_id}/feedback")
async def submit_feedback(
    entry_id: str,
    helpful: bool,
    user: Annotated[dict, Depends(require_role("technician"))],
):
    async with get_db() as db:
        row = await (await db.execute(
            "SELECT id FROM knowledge_entries WHERE id=?", (entry_id,)
        )).fetchone()
        if not row:
            raise HTTPException(404, "Entry not found")

        now = datetime.now(timezone.utc).isoformat()
        # Upsert feedback
        await db.execute(
            "INSERT INTO knowledge_feedback (entry_id, user_id, helpful, created_at)"
            " VALUES (?,?,?,?)"
            " ON CONFLICT(entry_id, user_id) DO UPDATE SET helpful=excluded.helpful",
            (entry_id, user["id"], helpful, now),
        )
        # Recompute vote totals
        counts = await (await db.execute(
            "SELECT SUM(CASE WHEN helpful=TRUE THEN 1 ELSE 0 END) AS hv,"
            " SUM(CASE WHEN helpful=FALSE THEN 1 ELSE 0 END) AS uhv"
            " FROM knowledge_feedback WHERE entry_id=?",
            (entry_id,),
        )).fetchone()
        await db.execute(
            "UPDATE knowledge_entries SET helpful_votes=?, unhelpful_votes=? WHERE id=?",
            (counts["hv"] or 0, counts["uhv"] or 0, entry_id),
        )
        await db.commit()
    return {"ok": True, "helpful_votes": counts["hv"] or 0, "unhelpful_votes": counts["uhv"] or 0}
