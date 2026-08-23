"""
Chroma vector database — stores and searches scheme chunks.

Flow:
  BUILD:  chunks → embeddings → save in data/chroma/
  SEARCH: user question → embedding → find nearest chunks in Chroma
"""

from __future__ import annotations

import logging
from typing import Optional

import chromadb

from app.core.config import settings
from app.knowledge.scheme_loader import SchemeRecord, load_schemes
from app.rag.embeddings import get_embedding_client
from app.rag.filters import build_chroma_filter, filter_schemes, get_matching_slugs
from app.rag.models import RetrievedChunk, SchemeChunk, SearchFilters

logger = logging.getLogger(__name__)


class ChromaVectorStore:

    def __init__(self) -> None:
        self._client: Optional[chromadb.ClientAPI] = None
        self._collection: Optional[chromadb.Collection] = None
        self._schemes: list[SchemeRecord] = []

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_ready(self) -> bool:
        return self._collection is not None and self.count > 0

    @property
    def count(self) -> int:
        if self._collection is None:
            return 0
        return self._collection.count()

    # ------------------------------------------------------------------
    # Connect / reset
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open (or create) the Chroma database on disk."""
        settings.chroma_persist_path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(settings.chroma_persist_path))
        self._collection = self._client.get_or_create_collection(
            name=settings.chroma_collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._schemes = load_schemes()
        logger.info("Chroma ready: %d chunks in '%s'", self.count, settings.chroma_collection_name)

    def reset(self) -> None:
        """Delete and recreate the collection (used when rebuilding index)."""
        if self._client is None:
            self.connect()
        try:
            self._client.delete_collection(settings.chroma_collection_name)  # type: ignore[union-attr]
        except Exception:
            pass
        self._collection = self._client.get_or_create_collection(  # type: ignore[union-attr]
            name=settings.chroma_collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    # ------------------------------------------------------------------
    # Build index
    # ------------------------------------------------------------------

    def add_chunks(self, chunks: list[SchemeChunk]) -> None:
        """Embed all chunks and save them in Chroma."""
        if not chunks:
            raise ValueError("No chunks to index")
        if self._collection is None:
            self.connect()

        embedder = get_embedding_client()
        texts = [c.embedding_text() for c in chunks]
        vectors = embedder.embed_many(texts)

        batch = settings.embedding_batch_size
        for i in range(0, len(chunks), batch):
            batch_chunks = chunks[i : i + batch]
            batch_vectors = vectors[i : i + batch]
            self._collection.upsert(  # type: ignore[union-attr]
                ids=[c.chunk_id for c in batch_chunks],
                embeddings=batch_vectors,
                documents=[c.content for c in batch_chunks],
                metadatas=[c.to_metadata() for c in batch_chunks],
            )
            logger.info("Saved %d / %d chunks to Chroma", min(i + batch, len(chunks)), len(chunks))

    # Alias for indexer
    upsert_chunks = add_chunks
    reset_collection = reset

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        filters: Optional[SearchFilters] = None,
        top_k: Optional[int] = None,
    ) -> list[RetrievedChunk]:
        """
        Find the most relevant chunks for a user question.

        Steps:
          1. Apply structured filters (state, ministry, …) → slug list
          2. Embed the query
          3. Query Chroma for nearest vectors
          4. Return top-K chunks with scores
        """
        if self._collection is None:
            raise RuntimeError("Call connect() first")
        if self.count == 0:
            logger.warning("Chroma is empty — run: python -m app.rag.indexer --build")
            return []

        filters = filters or SearchFilters()
        k = top_k or settings.rag_top_k

        # Step 1: structured pre-filter
        slug_list: list[str] = []
        has_structured_filter = bool(
            filters.state or filters.ministry or filters.beneficiary
            or filters.category or filters.slugs
        )
        if has_structured_filter:
            slug_list = get_matching_slugs(self._schemes, filters)
            if not slug_list:
                return []

        chroma_filter = build_chroma_filter(filters, slug_list)

        # Step 2: embed query
        query_vector = get_embedding_client().embed_one(query)

        # Step 3: query Chroma
        kwargs: dict = {
            "query_embeddings": [query_vector],
            "n_results": k,
            "include": ["documents", "metadatas", "distances"],
        }
        if chroma_filter:
            kwargs["where"] = chroma_filter

        try:
            raw = self._collection.query(**kwargs)  # type: ignore[union-attr]
        except Exception as exc:
            logger.warning("Chroma filter query failed, searching without filter: %s", exc)
            raw = self._collection.query(  # type: ignore[union-attr]
                query_embeddings=[query_vector],
                n_results=k,
                include=["documents", "metadatas", "distances"],
            )

        return self._parse_results(raw, filters, k)

    def _parse_results(self, raw: dict, filters: SearchFilters, top_k: int) -> list[RetrievedChunk]:
        """Convert Chroma response into RetrievedChunk objects."""
        ids        = (raw.get("ids")        or [[]])[0]
        documents  = (raw.get("documents")  or [[]])[0]
        metadatas  = (raw.get("metadatas")  or [[]])[0]
        distances  = (raw.get("distances")  or [[]])[0]

        chunks: list[RetrievedChunk] = []
        for i, chunk_id in enumerate(ids):
            meta = metadatas[i] or {}
            distance = float(distances[i]) if distances else 1.0
            chunks.append(RetrievedChunk(
                chunk_id=chunk_id,
                scheme_name=meta.get("scheme_name", ""),
                slug=meta.get("slug", ""),
                ministry=meta.get("ministry", ""),
                state=meta.get("state", ""),
                beneficiary=meta.get("beneficiary", ""),
                category=meta.get("category", ""),
                level=meta.get("level", ""),
                section=meta.get("section", ""),
                content=documents[i] or "",
                source_url=meta.get("source_url", ""),
                score=max(0.0, 1.0 - distance),  # convert distance → similarity
            ))

        if filters.is_empty():
            return chunks[:top_k]

        # Extra safety: re-check structured filters in Python
        by_slug = {s.slug: s for s in self._schemes}
        scheme_rows = [by_slug[c.slug] for c in chunks if c.slug in by_slug]
        allowed = {s.slug for s in filter_schemes(scheme_rows, filters)}
        return [c for c in chunks if c.slug in allowed][:top_k]


# Single shared instance used everywhere
vector_store = ChromaVectorStore()
