"""Knowledge base REST endpoints."""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from androbugger.auth.middleware import get_current_user, require_role
from androbugger.knowledge.indexer import search_knowledge
from androbugger.knowledge.store import get_store

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


class SearchRequest(BaseModel):
    query: str
    namespace: str | None = None
    device_model: str | None = None
    firmware_version: str | None = None
    top_k: int = 8


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
