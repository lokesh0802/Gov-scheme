"""
LangChain OpenAI client — used by all LangGraph agent nodes for LLM calls.
"""

from __future__ import annotations

import logging
from typing import Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

_llm: ChatOpenAI | None = None


def _base_llm() -> ChatOpenAI | None:
    if not settings.openai_api_key:
        return None
    global _llm
    if _llm is None:
        _llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.2,
        )
    return _llm


def ask_llm(
    system_prompt: str,
    user_prompt: str,
    history: Optional[list[dict[str, str]]] = None,
    max_tokens: int = 700,
) -> Optional[str]:
    llm = _base_llm()
    if llm is None:
        return None

    messages = [SystemMessage(content=system_prompt)]
    if history:
        for turn in history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role == "assistant":
                messages.append(AIMessage(content=content))
            else:
                messages.append(HumanMessage(content=content))
    messages.append(HumanMessage(content=user_prompt))

    try:
        response = llm.invoke(messages, max_tokens=max_tokens)
        return (response.content or "").strip()
    except Exception:
        logger.exception("LangChain OpenAI call failed")
        return None
