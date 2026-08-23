"""
Build and load the Chroma search index.

Run manually:
    python -m app.rag.indexer --build

Or let the server build it automatically on startup (BUILD_INDEX_IF_MISSING=true).
"""

from __future__ import annotations

import argparse
import logging

from app.core.config import settings
from app.knowledge.scheme_loader import load_schemes
from app.rag.chunker import chunk_all_schemes
from app.rag.vector_store import vector_store

logger = logging.getLogger(__name__)


def rebuild_index() -> int:
    """Full rebuild: read CSV → chunk → embed → save to Chroma."""
    logger.info("Building index from %s", settings.schemes_csv_path)
    schemes = load_schemes()
    chunks = chunk_all_schemes(schemes)

    vector_store.connect()
    vector_store.reset()
    vector_store.add_chunks(chunks)

    logger.info("Done — %d chunks indexed", vector_store.count)
    return vector_store.count


def ensure_index_loaded() -> None:
    """Called on server startup. Builds index if missing."""
    vector_store.connect()

    if settings.rebuild_index_on_startup:
        rebuild_index()
        return

    if vector_store.count > 0:
        logger.info("Chroma index already loaded (%d chunks)", vector_store.count)
        return

    if not settings.build_index_if_missing:
        logger.warning("Chroma is empty. Run: python -m app.rag.indexer --build")
        return

    if not settings.openai_api_key:
        logger.warning("Chroma empty and no OPENAI_API_KEY — search unavailable")
        return

    logger.info("Building index for the first time…")
    rebuild_index()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Build Chroma index for gov schemes")
    parser.add_argument("--build", action="store_true", help="Rebuild the index from CSV")
    args = parser.parse_args()

    if args.build:
        count = rebuild_index()
        print(f"Success: {count} chunks saved to {settings.chroma_persist_path}")
    else:
        ensure_index_loaded()
        print(f"Chroma ready: {vector_store.count} chunks")


if __name__ == "__main__":
    main()
