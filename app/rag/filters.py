"""
Structured filters — narrow schemes BEFORE vector search.

Example:
  User asks: "education scholarship in Karnataka"
  Router extracts: state="Karnataka", category="Education"
  This file filters the CSV rows first, then Chroma only searches those schemes.
"""

from __future__ import annotations

import logging
import re

from app.knowledge.scheme_loader import SchemeRecord
from app.rag.models import SearchFilters

logger = logging.getLogger(__name__)


def _lower(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _text_matches(haystack: str, needle: str) -> bool:
    """Case-insensitive partial match. 'All' or 'All India' matches everything."""
    if not needle:
        return True
    if _lower(needle) in {"all", "all india", "pan india"}:
        return True
    h, n = _lower(haystack), _lower(needle)
    return n in h or h in n


def filter_schemes(records: list[SchemeRecord], filters: SearchFilters) -> list[SchemeRecord]:
    """Return only schemes that match the given filters."""
    if filters.is_empty():
        return records

    result = records

    # Filter by explicit slug list (used when comparing specific schemes)
    if filters.slugs:
        allowed = {s.lower() for s in filters.slugs}
        result = [r for r in result if r.slug.lower() in allowed]

    filtered = []
    for record in result:
        if filters.state and not (
            _text_matches(record.beneficiary_state, filters.state)
            or _text_matches(record.state, filters.state)
        ):
            continue
        if filters.ministry and not _text_matches(record.ministry, filters.ministry):
            continue
        if filters.beneficiary and not (
            _text_matches(record.target_beneficiaries, filters.beneficiary)
            or _text_matches(record.scheme_for, filters.beneficiary)
        ):
            continue
        if filters.category and not _text_matches(record.categories, filters.category):
            continue
        if filters.level and not _text_matches(record.level, filters.level):
            continue
        filtered.append(record)

    logger.debug("Filter %d → %d schemes", len(records), len(filtered))
    return filtered


def get_matching_slugs(records: list[SchemeRecord], filters: SearchFilters) -> list[str]:
    """Get slug list after structured filtering (passed to Chroma)."""
    return [r.slug for r in filter_schemes(records, filters) if r.slug]


def build_chroma_filter(filters: SearchFilters, slug_list: list[str]) -> dict | None:
    """
    Build Chroma 'where' clause for metadata filtering.

    Chroma supports exact match and $in — not partial text search.
    Partial matching is done in filter_schemes() above.
    """
    parts: list[dict] = []

    if filters.section:
        parts.append({"section": filters.section})
    if filters.level:
        parts.append({"level": filters.level})
    if slug_list:
        parts.append({"slug": {"$in": slug_list[:2000]}})

    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return {"$and": parts}


# Keep old names for compatibility
slugs_from_filters = get_matching_slugs
build_chroma_where = build_chroma_filter
