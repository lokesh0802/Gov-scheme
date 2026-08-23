"""
Build an ordered list of unique schemes from retrieved chunks.

The display order (1, 2, 3…) must match last_search_slugs exactly.
"""

from __future__ import annotations

import re

from app.rag.models import RetrievedChunk

_SCHEME_URL_RE = re.compile(r"myscheme\.gov\.in/schemes/([a-z0-9-]+)", re.IGNORECASE)
_LIST_FOOTER_MARKERS = ("for full details", "reply *1*", "reply 1")


def unique_schemes_ordered(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """One entry per scheme slug, in the same order as search ranking."""
    seen: set[str] = set()
    ordered: list[RetrievedChunk] = []
    for chunk in chunks:
        if not chunk.slug or chunk.slug in seen:
            continue
        seen.add(chunk.slug)
        ordered.append(chunk)
    return ordered


def slugs_from_list_message(text: str) -> list[str]:
    """Recover scheme slugs from a numbered list reply (URLs in order)."""
    if not text:
        return []
    seen: set[str] = set()
    slugs: list[str] = []
    for match in _SCHEME_URL_RE.finditer(text):
        slug = match.group(1).lower()
        if slug not in seen:
            seen.add(slug)
            slugs.append(slug)
    return slugs


def is_scheme_list_reply(text: str) -> bool:
    """True if assistant message looks like a numbered scheme picker list."""
    if not text:
        return False
    lower = text.lower()
    if not any(marker in lower for marker in _LIST_FOOTER_MARKERS):
        return False
    return bool(_SCHEME_URL_RE.search(text))


def pending_search_slugs(last_search_slugs: list[str], messages: list) -> list[str]:
    """Slugs for 1/2/3 selection — from state or parsed from last list message."""
    if last_search_slugs:
        return last_search_slugs
    for msg in reversed(messages):
        if getattr(msg, "role", None) == "assistant":
            slugs = slugs_from_list_message(getattr(msg, "content", "") or "")
            if slugs:
                return slugs
            break
    return []
