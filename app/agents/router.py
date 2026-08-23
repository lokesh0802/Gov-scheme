"""
Router Agent — decides WHAT the user wants and extracts search filters.

Input:  user message + conversation state
Output: RouterResult (intent + filters + scheme names)
"""

from __future__ import annotations

import json
import logging
import re

from app.agents.llm import ask_llm
from app.agents.prompts import (
    STATUS_APPLICATION,
    STATUS_COMPARE,
    STATUS_DETAIL,
    STATUS_ELIGIBILITY,
    STATUS_SEARCH,
    STATUS_SELECT,
)
from app.agents.scheme_list import pending_search_slugs
from app.agents.types import Intent, RouterResult
from app.rag.models import SearchFilters
from app.storage.conversations import ConversationState

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ Keyword rules (fast, no API call)
GREETING_WORDS  = {"hi", "hello", "hey", "namaste", "start", "menu", "hii"}
HELP_WORDS      = ("help", "what can you do", "commands")
ELIGIBILITY_WORDS = ("eligible", "eligibility", "qualify", "am i eligible", "can i apply")
COMPARE_WORDS   = ("compare", " vs ", " versus ", "difference between")
APPLICATION_WORDS = ("apply", "application", "how to apply", "register", "documents required")
DETAIL_WORDS    = ("about", "details", "tell me more", "explain", "what is", "information about")
SEARCH_WORDS    = ("scheme", "schemes", "find", "search", "loan", "scholarship", "subsidy", "benefit", "grant")

INDIAN_STATES = [
    "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh",
    "goa", "gujarat", "haryana", "himachal pradesh", "jharkhand", "karnataka",
    "kerala", "madhya pradesh", "maharashtra", "manipur", "meghalaya", "mizoram",
    "nagaland", "odisha", "punjab", "rajasthan", "sikkim", "tamil nadu",
    "telangana", "tripura", "uttar pradesh", "uttarakhand", "west bengal",
    "delhi", "jammu and kashmir", "ladakh", "puducherry", "chandigarh",
]

CATEGORIES = [
    "education", "agriculture", "business", "entrepreneurship", "skill",
    "employment", "women", "child", "social welfare", "health", "housing",
    "farmer", "student", "loan", "scholarship",
]


def status_while_processing(message: str, state: ConversationState) -> str | None:
    """
    Quick status text to send before slow RAG/LLM work.
    Uses keyword rules only — no API call. Not saved to chat history.
    """
    text = message.lower().strip()
    if not text:
        return None

    if text in GREETING_WORDS or any(w in text for w in ("good morning", "good evening")):
        return None
    if any(w in text for w in HELP_WORDS):
        return None
    if any(w in text for w in ("feedback", "rate this", "review")):
        return None

    if pending_search_slugs(state.last_search_slugs, state.messages) and text.isdigit():
        return STATUS_SELECT
    if any(w in text for w in COMPARE_WORDS):
        return STATUS_COMPARE
    if any(w in text for w in ELIGIBILITY_WORDS):
        return STATUS_ELIGIBILITY
    if any(w in text for w in APPLICATION_WORDS):
        return STATUS_APPLICATION
    if any(w in text for w in DETAIL_WORDS):
        return STATUS_DETAIL

    # Any other message likely triggers search + optional LLM
    return STATUS_SEARCH


def route(message: str, state: ConversationState) -> RouterResult:
    text = message.lower().strip()

    # User picked a number from search results (state or last list message)
    if text.isdigit() and pending_search_slugs(state.last_search_slugs, state.messages):
        return RouterResult(intent=Intent.SELECT)

    # Greeting
    if text in GREETING_WORDS or any(w in text for w in ("good morning", "good evening")):
        return RouterResult(intent=Intent.GREETING)

    if any(w in text for w in HELP_WORDS):
        return RouterResult(intent=Intent.HELP)

    if any(w in text for w in ("feedback", "rate this", "review")):
        return RouterResult(intent=Intent.FEEDBACK)

    if any(w in text for w in COMPARE_WORDS):
        names = _extract_scheme_names(message)
        return RouterResult(intent=Intent.COMPARE, scheme_names=names, filters=_keyword_filters(text))

    if any(w in text for w in ELIGIBILITY_WORDS):
        return RouterResult(
            intent=Intent.ELIGIBILITY,
            filters=SearchFilters(section="eligibility"),
        )

    if any(w in text for w in APPLICATION_WORDS):
        return RouterResult(
            intent=Intent.APPLICATION,
            filters=SearchFilters(section="application_process"),
        )

    # Browse / find schemes — before DETAIL so "schemes about education" is search, not detail
    if any(w in text for w in SEARCH_WORDS):
        return RouterResult(intent=Intent.SEARCH, filters=_keyword_filters(text))

    if any(w in text for w in DETAIL_WORDS):
        names = _extract_scheme_names(message)
        return RouterResult(intent=Intent.DETAIL, scheme_names=names)

    # Fallback: ask LLM to classify (if API key available)
    llm_result = _llm_route(message, state)
    if llm_result:
        return llm_result

    # Default: treat as search
    return RouterResult(intent=Intent.SEARCH, filters=_keyword_filters(text))


def _keyword_filters(text: str) -> SearchFilters:
    """Extract state and category from message. Priority order matters."""
    state = next((s.title() for s in INDIAN_STATES if s in text), None)

    # First matching keyword wins (most specific first).
    # Use None for category = no category filter (semantic search only).
    category_rules: list[tuple[str, str | None]] = [
        ("education loan", "Education"),
        ("student loan", "Education"),
        ("scholarship", "Education"),
        ("skill training", "Skills"),
        ("women entrepreneur", "Business"),
        ("farmer", "Agriculture"),
        ("agriculture", "Agriculture"),
        ("education", "Education"),
        ("loan", None),          # generic loan — don't narrow by category
        ("scholarship", "Education"),
        ("student", "Education"),
        ("business", "Business"),
        ("employment", "Skills"),
    ]
    category: str | None = None
    for keyword, cat in category_rules:
        if keyword in text:
            category = cat
            break

    return SearchFilters(state=state, category=category)


def _extract_scheme_names(message: str) -> list[str]:
    """Pull quoted or 'vs'-separated scheme names from message."""
    quoted = re.findall(r'"([^"]+)"', message)
    if quoted:
        return quoted
    if " vs " in message.lower():
        parts = re.split(r"\s+vs\s+", message, flags=re.IGNORECASE)
        return [p.strip() for p in parts if p.strip()]
    return []


def _llm_route(message: str, state: ConversationState) -> RouterResult | None:
    prompt = f"""Classify this WhatsApp message for a government schemes bot.
Message: "{message}"
Active scheme: {state.active_scheme_slug or "none"}

Return JSON only:
{{
  "intent": "greeting|help|search|detail|eligibility|compare|application|feedback",
  "state": "state name or null",
  "category": "category or null",
  "scheme_names": ["name1", "name2"]
}}"""
    raw = ask_llm("You classify user intents. Reply with JSON only.", prompt, max_tokens=100)
    if not raw:
        return None
    try:
        data = json.loads(raw)
        intent = Intent(data.get("intent", "search"))
        filters = SearchFilters(
            state=data.get("state"),
            category=data.get("category"),
        )
        return RouterResult(
            intent=intent,
            filters=filters,
            scheme_names=data.get("scheme_names") or [],
        )
    except Exception:
        logger.warning("LLM router returned invalid JSON: %s", raw)
        return None


# ------------------------------------------------------------------ LangGraph node


def route_node(state: "GovGraphState") -> dict:
    """LangGraph node: classify intent and extract filters."""
    from app.agents.graph_state import GovGraphState

    if state.get("conversation_saved"):
        return {}

    conv = state["conversation"]
    route_result = route(state["user_message"], conv)
    logger.info(
        "chat=%s intent=%s first_contact=%s",
        state["chat_id"],
        route_result.intent.value,
        conv.is_first_contact,
    )
    return {"router": route_result}
