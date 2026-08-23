"""
Retrieval Agent — searches Chroma for relevant scheme chunks.

Input:  user query + SearchFilters
Output: list of RetrievedChunk (top-K most relevant pieces)
"""

from __future__ import annotations

import logging

from app.agents.types import RouterResult
from app.core.config import settings
from app.rag.models import RetrievedChunk, SearchFilters
from app.rag.vector_store import vector_store

logger = logging.getLogger(__name__)


def retrieve(query: str, router: RouterResult, top_k: int = None) -> list[RetrievedChunk]:
    """
    Run the full retrieval pipeline:
      1. Connect to Chroma (if not already)
      2. Apply structured filters from router
      3. Semantic search
      4. Return top-K chunks
    """
    if not vector_store.is_ready:
        try:
            vector_store.connect()
        except Exception:
            logger.exception("Could not connect to Chroma")
            return []

    if vector_store.count == 0:
        logger.warning("Chroma index is empty")
        return []

    k = top_k or settings.rag_top_k
    filters = router.filters or SearchFilters()

    # If router found specific scheme names, search using those as the query
    search_query = query
    if router.scheme_names:
        search_query = " ".join(router.scheme_names) + " " + query

    chunks = vector_store.search(search_query, filters=filters, top_k=k)

    # If strict filters found nothing, retry with semantic search only
    if not chunks and not filters.is_empty():
        logger.info("No results with filters %s — retrying without filters", filters)
        chunks = vector_store.search(search_query, filters=SearchFilters(), top_k=k)

    logger.info("Retrieved %d chunks for query=%r", len(chunks), query[:60])
    return chunks


def retrieve_for_slug(slug: str, top_k: int = 10) -> list[RetrievedChunk]:
    """Load all sections for one scheme slug."""
    from app.agents.types import Intent, RouterResult

    route = RouterResult(intent=Intent.DETAIL, filters=SearchFilters(slugs=[slug]))
    chunks = retrieve(slug, route, top_k=top_k)
    return [c for c in chunks if c.slug == slug] or chunks


# ------------------------------------------------------------------ LangGraph node


def retrieve_node(state: "GovGraphState") -> dict:
    """LangGraph node: semantic search in Chroma."""
    if state.get("conversation_saved"):
        return {}
    route_result = state["router"]
    chunks = retrieve(state["user_message"], route_result)
    return {"chunks": chunks}


def format_chunks_for_llm(chunks: list[RetrievedChunk]) -> str:
  """Format retrieved chunks as context text for the LLM."""
  if not chunks:
      return "No relevant information found."

  parts = []
  for i, chunk in enumerate(chunks, 1):
      parts.append(
          f"--- Chunk {i} ---\n"
          f"Scheme: {chunk.scheme_name}\n"
          f"Section: {chunk.section}\n"
          f"Ministry: {chunk.ministry} | State: {chunk.state} | Level: {chunk.level}\n"
          f"URL: {chunk.source_url}\n"
          f"Content:\n{chunk.content}"
      )
  return "\n\n".join(parts)
