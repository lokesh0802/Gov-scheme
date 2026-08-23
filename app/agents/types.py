"""
Shared types for all agents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.rag.models import RetrievedChunk, SearchFilters


class Intent(str, Enum):
    GREETING    = "greeting"
    HELP        = "help"
    SEARCH      = "search"        # find schemes
    DETAIL      = "detail"        # explain one scheme
    ELIGIBILITY = "eligibility"   # am I eligible?
    COMPARE     = "compare"       # compare two or more schemes
    APPLICATION = "application"   # how to apply
    SELECT      = "select"        # pick a number from search results
    FEEDBACK    = "feedback"


@dataclass
class RouterResult:
    """Output of the Router Agent."""
    intent: Intent
    filters: SearchFilters = field(default_factory=SearchFilters)
    scheme_names: list[str] = field(default_factory=list)   # for compare/detail


@dataclass
class AgentContext:
    """Everything an agent needs to do its job."""
    user_message: str
    chat_id: str
    router: RouterResult
    chunks: list[RetrievedChunk] = field(default_factory=list)
    history: list[dict[str, str]] = field(default_factory=list)
    user_profile: dict = field(default_factory=dict)
