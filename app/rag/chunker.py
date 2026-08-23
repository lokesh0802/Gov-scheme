"""
Split each scheme into 6 small chunks (one per section).

WHY chunk?
  Embedding an entire scheme (~8 KB) gives poor search results.
  Splitting lets "am I eligible?" match only Eligibility text.

SECTIONS created per scheme:
  description | benefits | eligibility | documents_required | application_process | faqs
"""

from __future__ import annotations

import logging
import re

from app.knowledge.scheme_loader import SchemeRecord
from app.rag.models import SchemeChunk

logger = logging.getLogger(__name__)

# Skip sections shorter than this (empty or useless)
MIN_CHUNK_CHARS = 40

# (section name in Chroma, field name on SchemeRecord)
SECTIONS = [
    ("description",         "details_md"),
    ("benefits",            "benefits_md"),
    ("eligibility",         "eligibility_md"),
    ("documents_required",  "documents_md"),
    ("application_process", "application_md"),
    ("faqs",                "faqs_md"),
]


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def chunk_one_scheme(record: SchemeRecord) -> list[SchemeChunk]:
    """Turn one scheme into 0–6 chunks (skips empty sections)."""
    chunks = []
    shared = dict(
        scheme_name=record.name,
        slug=record.slug,
        ministry=record.ministry or "Unknown",
        state=record.beneficiary_state or record.state or "All",
        beneficiary=record.target_beneficiaries or record.scheme_for or "",
        category=(record.categories.split(",")[0].strip() if record.categories else ""),
        level=record.level or "Unknown",
        source_url=record.url,
    )

    for section_name, field_name in SECTIONS:
        text = _clean(getattr(record, field_name, ""))
        if len(text) < MIN_CHUNK_CHARS:
            continue
        chunks.append(SchemeChunk(
            chunk_id=f"{record.slug}::{section_name}",
            section=section_name,
            content=text,
            **shared,
        ))
    return chunks


def chunk_all_schemes(records: list[SchemeRecord]) -> list[SchemeChunk]:
    """Chunk every scheme. Called once when building the Chroma index."""
    all_chunks: list[SchemeChunk] = []
    for record in records:
        if not record.slug:
            logger.warning("Skipping scheme without slug: %s", record.name)
            continue
        all_chunks.extend(chunk_one_scheme(record))

    logger.info("Created %d chunks from %d schemes", len(all_chunks), len(records))
    return all_chunks

# Keep old names so other files don't break
chunk_scheme = chunk_one_scheme
chunk_schemes = chunk_all_schemes
