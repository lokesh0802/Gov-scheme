"""
Shared helpers for LangGraph agent nodes.
"""

from __future__ import annotations

from app.agents.graph_state import GovGraphState
from app.agents.types import AgentContext
from app.storage.conversations import save_conversation

WHATSAPP_MAX = 4000


def split_reply(text: str) -> list[str]:
    """Split long replies into WhatsApp-safe parts."""
    if len(text) <= WHATSAPP_MAX:
        return [text]
    parts, remaining = [], text
    while remaining:
        if len(remaining) <= WHATSAPP_MAX:
            parts.append(remaining)
            break
        cut = remaining.rfind("\n", 0, WHATSAPP_MAX)
        if cut <= 0:
            cut = WHATSAPP_MAX
        parts.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    return parts


def agent_context(state: GovGraphState) -> AgentContext:
    """Build AgentContext from current graph state."""
    conv = state["conversation"]
    route = state["router"]
    return AgentContext(
        user_message=state["user_message"],
        chat_id=state["chat_id"],
        router=route,
        chunks=state.get("chunks") or [],
        history=conv.history(),
        user_profile=conv.user_profile.model_dump(),
    )


def save_static_reply(state: GovGraphState, reply: str) -> dict:
    """Persist a fixed reply (greeting, help, errors) and mark graph done."""
    conv = state["conversation"]
    conv.add_message("user", state["user_message"])
    conv.add_message("assistant", reply)
    save_conversation(conv)
    return {
        "reply": reply,
        "parts": split_reply(reply),
        "conversation_saved": True,
    }
