"""
LangGraph shared state for the GovScheme multi-agent pipeline.

Each agent module exports a `*_node(state)` function that reads/writes this state.
"""

from __future__ import annotations

from typing_extensions import TypedDict

from app.agents.types import RouterResult
from app.rag.models import RetrievedChunk
from app.storage.conversations import ConversationState


class GovGraphState(TypedDict, total=False):
    """State passed between LangGraph nodes."""

    chat_id: str
    user_message: str
    conversation: ConversationState
    router: RouterResult
    chunks: list[RetrievedChunk]
    reply: str
    parts: list[str]
    prepend_parts: list[str]
    user_already_saved: bool
    conversation_saved: bool
