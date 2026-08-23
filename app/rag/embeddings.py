"""
Convert text to vectors using OpenAI embeddings.

Used in two places:
  1. Building the index  → embed every chunk once
  2. Searching           → embed the user's question each time
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from openai import OpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingClient:
    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is missing. Add it to your .env file.")
        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_embedding_model
        self._batch_size = settings.embedding_batch_size

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts in batches (for index building)."""
        if not texts:
            return []
        all_vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            all_vectors.extend(self._call_api(batch))
            done = min(start + len(batch), len(texts))
            logger.info("Embedded %d / %d", done, len(texts))
        return all_vectors

    def embed_one(self, text: str) -> list[float]:
        """Embed a single text (for search queries)."""
        return self._call_api([text])[0]

    # Aliases used by vector_store.py
    embed_texts = embed_many
    embed_query = embed_one

    def _call_api(self, texts: list[str], retries: int = 3) -> list[list[float]]:
        last_error: Optional[Exception] = None
        for attempt in range(1, retries + 1):
            try:
                response = self._client.embeddings.create(model=self._model, input=texts)
                return [item.embedding for item in response.data]
            except Exception as exc:
                last_error = exc
                logger.warning("Embedding failed (attempt %d): %s", attempt, exc)
                time.sleep(attempt * 2)
        raise RuntimeError(f"Embedding failed after {retries} attempts") from last_error


# Single shared instance (created on first use)
_client: Optional[EmbeddingClient] = None


def get_embedding_client() -> EmbeddingClient:
    global _client
    if _client is None:
        _client = EmbeddingClient()
    return _client
