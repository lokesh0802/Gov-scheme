"""
LangGraph nodes: load conversation, first-message prep, index check, finalize.
"""

from __future__ import annotations

from app.agents.graph_state import GovGraphState
from app.agents.graph_utils import save_static_reply, split_reply
from app.agents.prompts import NO_INDEX, WELCOME_FIRST_TIME
from app.rag.vector_store import vector_store
from app.storage.conversations import get_conversation, save_conversation


def load_node(state: GovGraphState) -> dict:
    text = (state.get("user_message") or "").strip()
    chat_id = state["chat_id"]
    conv = get_conversation(chat_id)

    if not text:
        reply = "Please send a message. Type *hi* to get started."
        return {
            "user_message": text,
            "conversation": conv,
            "reply": reply,
            "parts": split_reply(reply),
            "conversation_saved": True,
        }

    return {"user_message": text, "conversation": conv}


def first_query_prep_node(state: GovGraphState) -> dict:
    conv = state["conversation"]
    conv.add_message("user", state["user_message"])
    conv.add_message("assistant", WELCOME_FIRST_TIME)
    save_conversation(conv)
    return {
        "user_already_saved": True,
        "prepend_parts": split_reply(WELCOME_FIRST_TIME),
    }


def check_index_node(state: GovGraphState) -> dict:
    if vector_store.is_ready:
        return {}
    reply = NO_INDEX
    if state.get("user_already_saved"):
        return {"reply": reply, "parts": split_reply(reply), "conversation_saved": True}
    return save_static_reply(state, reply)


def finalize_node(state: GovGraphState) -> dict:
    if state.get("conversation_saved"):
        parts = list(state.get("prepend_parts") or []) + list(state.get("parts") or [])
        if parts:
            return {"parts": parts}
        reply = state.get("reply") or ""
        return {"parts": list(state.get("prepend_parts") or []) + split_reply(reply)}

    conv = state["conversation"]
    reply = state.get("reply") or ""

    if not state.get("user_already_saved"):
        conv.add_message("user", state["user_message"])
    conv.add_message("assistant", reply)
    save_conversation(conv)

    parts = list(state.get("prepend_parts") or []) + split_reply(reply)
    return {"parts": parts, "conversation_saved": True}
