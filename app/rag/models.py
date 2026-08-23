"""
Data models used by the RAG pipeline.

Read this file first if you want to understand what travels through the system:

  SchemeChunk      → one piece of a scheme (e.g. only the Eligibility section)
  SearchFilters    → optional filters (state, ministry, category, …)
  RetrievedChunk   → a chunk returned by Chroma with a similarity score
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# What we store in Chroma (one row in the vector database)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SchemeChunk:
    """One logical section of a government scheme, ready for embedding."""

    chunk_id: str          # e.g. "sui::eligibility"
    scheme_name: str
    slug: str
    ministry: str
    state: str
    beneficiary: str
    category: str
    level: str             # Central / State / UT
    section: str           # description | benefits | eligibility | …
    content: str           # the actual text for this section
    source_url: str

    def embedding_text(self) -> str:
        """Combined text sent to OpenAI for embedding (richer than content alone)."""
        return (
            f"Scheme: {self.scheme_name}\n"
            f"Section: {self.section}\n"
            f"Ministry: {self.ministry}\n"
            f"State: {self.state}\n"
            f"Beneficiary: {self.beneficiary}\n"
            f"Category: {self.category}\n"
            f"Level: {self.level}\n"
            f"Content: {self.content}"
        )

    def to_metadata(self) -> dict[str, str]:
        """Metadata stored alongside the vector in Chroma (used for filtering)."""
        return {
            "scheme_name": self.scheme_name,
            "slug": self.slug,
            "ministry": self.ministry,
            "state": self.state,
            "beneficiary": self.beneficiary,
            "category": self.category,
            "level": self.level,
            "section": self.section,
            "source_url": self.source_url,
        }


# ---------------------------------------------------------------------------
# Filters applied BEFORE semantic search
# ---------------------------------------------------------------------------

@dataclass
class SearchFilters:
    """
    Narrow down which schemes to search.

    Example: state="Karnataka", category="Education"
    → only Karnataka education schemes are searched in Chroma.
    """

    state: Optional[str] = None
    ministry: Optional[str] = None
    beneficiary: Optional[str] = None
    category: Optional[str] = None
    level: Optional[str] = None
    section: Optional[str] = None   # e.g. "eligibility" only
    slugs: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not any([
            self.state, self.ministry, self.beneficiary,
            self.category, self.level, self.section, self.slugs,
        ])


# ---------------------------------------------------------------------------
# What comes back from a search
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RetrievedChunk:
    """A chunk found by Chroma, with a relevance score."""

    chunk_id: str
    scheme_name: str
    slug: str
    ministry: str
    state: str
    beneficiary: str
    category: str
    level: str
    section: str
    content: str
    source_url: str
    score: float   # 0.0 – 1.0 (higher = more relevant)

    def citation(self) -> str:
        return f"{self.scheme_name} — {self.section} ({self.source_url})"
