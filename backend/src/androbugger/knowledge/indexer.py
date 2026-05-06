"""Index resolved diagnoses, vendor docs, and AOSP reference material."""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from androbugger.knowledge.embeddings import get_embedder
from androbugger.knowledge.store import get_store

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 1800  # chars per chunk (~450 tokens)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _chunk(text: str, size: int = _CHUNK_SIZE) -> list[str]:
    """Split text into overlapping chunks on paragraph boundaries."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) < size:
            current += ("\n\n" if current else "") + para
        else:
            if current:
                chunks.append(current)
            current = para
    if current:
        chunks.append(current)
    return chunks or [text[:size]]


def index_resolved_diagnosis(session: dict) -> list[str]:
    """
    Called automatically when a diagnostic session is marked 'resolved'.
    Returns list of created entry IDs.
    """
    root_cause = session.get("root_cause") or ""
    applied_fix = session.get("applied_fix") or ""
    if not root_cause or root_cause.lower() == "unknown":
        return []

    content = "\n\n".join(filter(None, [
        f"Root Cause: {root_cause}",
        f"Applied Fix: {applied_fix}",
        session.get("resolution_notes") or "",
        session.get("llm_report") or "",
        session.get("deterministic_summary") or "",
    ]))

    store = get_store()
    embedder = get_embedder()
    entry_ids: list[str] = []
    now = datetime.now(timezone.utc).isoformat()

    for i, chunk in enumerate(_chunk(content)):
        entry_id = str(uuid.uuid4())
        emb = embedder.embed(chunk)
        store.add(
            entry_id=entry_id,
            title=f"Case: {root_cause[:80]} [{session.get('device_model', '?')}]",
            content=chunk,
            embedding=emb,
            namespace="past_diagnoses",
            device_model=session.get("device_model"),
            firmware_version=session.get("firmware_version"),
            metadata={
                "session_id": session.get("id"),
                "root_cause": root_cause[:200],
                "applied_fix": applied_fix[:200],
                "resolved_at": now,
                "chunk_index": i,
            },
        )
        entry_ids.append(entry_id)

    logger.info("Indexed resolved session %s → %d knowledge chunks", session.get("id"), len(entry_ids))
    return entry_ids


def index_document(file_path: Path, title: str, namespace: str,
                   device_model: str | None = None,
                   firmware_version: str | None = None,
                   metadata: dict | None = None) -> list[str]:
    """Index a vendor doc, firmware note, or AOSP reference from a file."""
    if not file_path.exists():
        logger.warning("File not found: %s", file_path)
        return []

    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        text = _read_pdf(file_path)
    else:
        text = file_path.read_text(errors="replace")

    return _index_text(text, title, namespace, device_model, firmware_version, metadata or {})


def _read_pdf(path: Path) -> str:
    try:
        import fitz  # pymupdf
        doc = fitz.open(str(path))
        return "\n\n".join(page.get_text() for page in doc)
    except Exception as exc:
        logger.warning("PDF read failed for %s: %s", path, exc)
        return ""


def _index_text(text: str, title: str, namespace: str,
                device_model: str | None, firmware_version: str | None,
                metadata: dict) -> list[str]:
    store = get_store()
    embedder = get_embedder()
    entry_ids: list[str] = []

    for i, chunk in enumerate(_chunk(text)):
        entry_id = str(uuid.uuid4())
        emb = embedder.embed(chunk)
        store.add(
            entry_id=entry_id,
            title=f"{title} (part {i + 1})" if i else title,
            content=chunk,
            embedding=emb,
            namespace=namespace,
            device_model=device_model,
            firmware_version=firmware_version,
            metadata={**metadata, "chunk_index": i, "content_hash": _sha256(chunk)},
        )
        entry_ids.append(entry_id)

    logger.info("Indexed '%s' → %d chunks in namespace '%s'", title, len(entry_ids), namespace)
    return entry_ids


def search_knowledge(query: str, device_model: str | None = None,
                     namespace: str | None = None, top_k: int = 8) -> list[dict]:
    """Hybrid search convenience wrapper used by the diagnostic pipeline."""
    embedder = get_embedder()
    embedding = embedder.embed(query)
    return get_store().search(
        query=query,
        query_embedding=embedding,
        namespace=namespace,
        device_model=device_model,
        top_k=top_k,
    )
