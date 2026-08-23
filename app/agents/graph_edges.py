"""
LangGraph conditional routing — decides which agent node runs next.
"""

from __future__ import annotations

from app.agents.graph_state import GovGraphState
from app.agents.types import Intent


def after_load(state: GovGraphState) -> str:
    if state.get("conversation_saved"):
        return "finalize"
    return "route"


def after_route(state: GovGraphState) -> str:
    conv = state["conversation"]
    intent = state["router"].intent

    if conv.is_first_contact:
        if intent == Intent.GREETING:
            return "welcome_first"
        return "first_query"

    if intent == Intent.GREETING:
        return "welcome_back"
    if intent == Intent.HELP:
        return "help"
    if intent == Intent.FEEDBACK:
        return "feedback"
    if intent == Intent.SELECT:
        return "select"
    return "check_index"


def after_check_index(state: GovGraphState) -> str:
    if state.get("conversation_saved"):
        return "finalize"
    return "retrieve"


def after_retrieve(state: GovGraphState) -> str:
    intent = state["router"].intent
    if intent == Intent.ELIGIBILITY:
        return "eligibility"
    if intent == Intent.COMPARE:
        return "compare"
    if intent == Intent.SEARCH:
        return "search_list"
    if intent in (Intent.DETAIL, Intent.APPLICATION):
        return "detail_branch"
    return "default_branch"
