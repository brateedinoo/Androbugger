"""Local embedding generation via sentence-transformers or Ollama."""
import asyncio
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

_EMBEDDING_DIM = 768  # nomic-embed-text default


class EmbeddingGenerator:
    def __init__(self, model_name: str = "nomic-embed-text"):
        self._model_name = model_name
        self._model = None  # lazy load

    def _load(self):
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
            logger.info("Loaded embedding model: %s", self._model_name)
        except Exception as exc:
            logger.warning("Could not load sentence-transformers model %s: %s", self._model_name, exc)
            self._model = "fallback"

    def embed(self, text: str) -> list[float]:
        self._load()
        if self._model == "fallback" or self._model is None:
            return self._fallback_embed(text)
        try:
            vec = self._model.encode(text[:8192], normalize_embeddings=True)
            return vec.tolist()
        except Exception as exc:
            logger.warning("Embedding failed: %s", exc)
            return self._fallback_embed(text)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self._load()
        if self._model == "fallback" or self._model is None:
            return [self._fallback_embed(t) for t in texts]
        try:
            vecs = self._model.encode([t[:8192] for t in texts], normalize_embeddings=True)
            return [v.tolist() for v in vecs]
        except Exception as exc:
            logger.warning("Batch embedding failed: %s", exc)
            return [self._fallback_embed(t) for t in texts]

    @staticmethod
    def _fallback_embed(text: str) -> list[float]:
        """Deterministic zero-vector fallback when model is unavailable."""
        import hashlib
        h = int(hashlib.md5(text.encode()).hexdigest(), 16)
        # Produce a 768-dim near-zero vector seeded by content hash
        import math
        return [math.sin(h * (i + 1) * 1e-6) * 0.01 for i in range(_EMBEDDING_DIM)]


@lru_cache(maxsize=1)
def get_embedder() -> EmbeddingGenerator:
    from androbugger.config import settings
    return EmbeddingGenerator(settings.embedding_model)
