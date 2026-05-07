"""Hybrid BM25 + vector search store using ChromaDB + tantivy-py with RRF fusion."""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_RRF_K = 60  # standard RRF constant


class KnowledgeStore:
    def __init__(self, chroma_path: Path, tantivy_path: Path):
        self._chroma_path = chroma_path
        self._tantivy_path = tantivy_path
        self._chroma_client = None
        self._collection = None
        self._tantivy_index = None
        self._tantivy_writer = None
        self._init()

    def _init(self):
        # ChromaDB
        try:
            import chromadb
            self._chroma_path.mkdir(parents=True, exist_ok=True)
            self._chroma_client = chromadb.PersistentClient(path=str(self._chroma_path))
            self._collection = self._chroma_client.get_or_create_collection(
                name="androbugger_knowledge",
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("ChromaDB initialised at %s", self._chroma_path)
        except Exception as exc:
            logger.warning("ChromaDB unavailable: %s", exc)

        # tantivy-py
        try:
            import tantivy
            self._tantivy_path.mkdir(parents=True, exist_ok=True)
            schema_builder = tantivy.SchemaBuilder()
            schema_builder.add_text_field("entry_id", stored=True)
            schema_builder.add_text_field("title", stored=True)
            schema_builder.add_text_field("content", stored=True, tokenizer_name="en_stem")
            schema_builder.add_text_field("namespace", stored=True)
            schema_builder.add_text_field("device_model", stored=True)
            schema_builder.add_text_field("firmware_version", stored=True)
            schema = schema_builder.build()
            self._tantivy_index = tantivy.Index(schema, path=str(self._tantivy_path))
            logger.info("tantivy index initialised at %s", self._tantivy_path)
        except Exception as exc:
            logger.warning("tantivy unavailable: %s", exc)

    def add(self, entry_id: str, title: str, content: str, embedding: list[float],
            namespace: str, device_model: str | None = None,
            firmware_version: str | None = None, metadata: dict | None = None) -> None:
        meta = metadata or {}
        meta.update({"namespace": namespace, "device_model": device_model or "",
                     "firmware_version": firmware_version or "", "title": title})

        # ChromaDB
        if self._collection is not None:
            try:
                self._collection.upsert(
                    ids=[entry_id],
                    embeddings=[embedding],
                    documents=[content[:2000]],
                    metadatas=[{k: str(v) for k, v in meta.items()}],
                )
            except Exception as exc:
                logger.warning("ChromaDB add failed: %s", exc)

        # tantivy
        if self._tantivy_index is not None:
            try:
                writer = self._tantivy_index.writer()
                writer.add_document(self._tantivy_index.schema.parse_document({
                    "entry_id": entry_id,
                    "title": title,
                    "content": content[:4000],
                    "namespace": namespace,
                    "device_model": device_model or "",
                    "firmware_version": firmware_version or "",
                }))
                writer.commit()
            except Exception as exc:
                logger.warning("tantivy add failed: %s", exc)

    def search(self, query: str, query_embedding: list[float],
               namespace: str | None = None, device_model: str | None = None,
               top_k: int = 10) -> list[dict]:
        """Hybrid search: BM25 + vector → RRF fusion."""
        vector_results: list[tuple[str, float]] = []  # (entry_id, score)
        bm25_results: list[tuple[str, float]] = []

        # Vector search via ChromaDB
        if self._collection is not None:
            try:
                where: dict = {}
                if namespace:
                    where["namespace"] = namespace
                if device_model:
                    where["device_model"] = device_model
                q_params: dict = dict(
                    query_embeddings=[query_embedding],
                    n_results=min(top_k * 2, 50),
                    include=["documents", "metadatas", "distances"],
                )
                if where:
                    q_params["where"] = where
                results = self._collection.query(**q_params)
                ids = results.get("ids", [[]])[0]
                docs = results.get("documents", [[]])[0]
                metas = results.get("metadatas", [[]])[0]
                dists = results.get("distances", [[]])[0]
                for i, eid in enumerate(ids):
                    score = 1.0 - (dists[i] if dists else 0)
                    vector_results.append((eid, score))
                    self._doc_cache[eid] = (
                        metas[i].get("title", "") if metas else "",
                        docs[i][:300] if docs else "",
                        metas[i] if metas else {},
                    )
            except Exception as exc:
                logger.warning("ChromaDB search failed: %s", exc)

        # BM25 via tantivy
        if self._tantivy_index is not None:
            try:
                searcher = self._tantivy_index.searcher()
                qp = self._tantivy_index.parse_query(
                    query, ["title", "content"]
                )
                hits = searcher.search(qp, top_k * 2)
                for score, addr in hits.hits:
                    doc = searcher.doc(addr)
                    eid = doc.get_first("entry_id") or ""
                    if eid:
                        bm25_results.append((eid, float(score)))
                        if eid not in self._doc_cache:
                            self._doc_cache[eid] = (
                                doc.get_first("title") or "",
                                (doc.get_first("content") or "")[:300],
                                {"namespace": doc.get_first("namespace") or "",
                                 "device_model": doc.get_first("device_model") or ""},
                            )
            except Exception as exc:
                logger.warning("tantivy search failed: %s", exc)

        return self._rrf_merge(vector_results, bm25_results, top_k)

    # In-memory doc cache populated during searches
    _doc_cache: dict[str, tuple[str, str, dict]] = {}

    def _rrf_merge(self, v: list[tuple[str, float]], b: list[tuple[str, float]], top_k: int) -> list[dict]:
        scores: dict[str, float] = {}
        for rank, (eid, _) in enumerate(v):
            scores[eid] = scores.get(eid, 0) + 1.0 / (_RRF_K + rank + 1)
        for rank, (eid, _) in enumerate(b):
            scores[eid] = scores.get(eid, 0) + 1.0 / (_RRF_K + rank + 1)

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        results = []
        for eid, score in ranked:
            title, snippet, meta = self._doc_cache.get(eid, ("", "", {}))
            results.append({
                "entry_id": eid,
                "title": title,
                "content_snippet": snippet,
                "score": score,
                "namespace": meta.get("namespace", ""),
                "metadata": meta,
            })
        return results

    def delete(self, entry_id: str) -> None:
        if self._collection is not None:
            try:
                self._collection.delete(ids=[entry_id])
            except Exception:
                pass

    def get_stats(self) -> dict:
        total = 0
        by_ns: dict[str, int] = {}
        if self._collection is not None:
            try:
                total = self._collection.count()
                # Approximate namespace breakdown
                for ns in ("vendor_docs", "past_diagnoses", "aosp_reference"):
                    try:
                        r = self._collection.get(where={"namespace": ns})
                        by_ns[ns] = len(r.get("ids", []))
                    except Exception:
                        by_ns[ns] = 0
            except Exception:
                pass
        return {"total_entries": total, "by_namespace": by_ns}


_store: KnowledgeStore | None = None


def get_store() -> KnowledgeStore:
    global _store
    if _store is None:
        from androbugger.config import settings
        _store = KnowledgeStore(settings.chroma_path, settings.tantivy_path)
    return _store
