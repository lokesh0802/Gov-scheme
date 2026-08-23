"""
LangGraph nodes: fixed replies (no RAG / LLM).
"""

from __future__ import annotations

from app.agents.graph_state import GovGraphState
from app.agents.graph_utils import save_static_reply
from app.agents.prompts import FEEDBACK, HELP, WELCOME_BACK, WELCOME_FIRST_TIME


def welcome_first_node(state: GovGraphState) -> dict:
    return save_static_reply(state, WELCOME_FIRST_TIME)


def welcome_back_node(state: GovGraphState) -> dict:
    return save_static_reply(state, WELCOME_BACK)


def help_node(state: GovGraphState) -> dict:
    return save_static_reply(state, HELP)


def feedback_node(state: GovGraphState) -> dict:
    return save_static_reply(state, FEEDBACK)
