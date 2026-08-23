"""
Comparison Agent — compares two or more schemes side by side.

Triggered by: "compare Stand-Up India vs MUDRA"
"""

from __future__ import annotations

import logging

from app.agents.llm import ask_llm
from app.agents.prompts import COMPARISON_SYSTEM
from app.agents.retrieval import format_chunks_for_llm, retrieve
from app.agents.types import AgentContext, RouterResult
from app.rag.models import SearchFilters
from app.whatsapp.formatting import format_for_whatsapp

logger = logging.getLogger(__name__)


def run(ctx: AgentContext) -> str:
    scheme_names = ctx.router.scheme_names

    if len(scheme_names) < 2:
        # Try to find schemes from chunks already retrieved
        slugs = list({c.slug for c in ctx.chunks})
        if len(slugs) < 2:
            return (
                "Please name the schemes you want to compare.\n"
                "Example: *compare Stand-Up India vs MUDRA*"
            )
        scheme_names = list({c.scheme_name for c in ctx.chunks})[:2]

    # Retrieve chunks for each scheme separately
    all_chunks = []
    for name in scheme_names[:3]:   # max 3 schemes
        router = RouterResult(
            intent=ctx.router.intent,
            scheme_names=[name],
            filters=SearchFilters(),
        )
        chunks = retrieve(name, router, top_k=4)
        all_chunks.extend(chunks)

    if not all_chunks:
        return f"I couldn't find information for: {', '.join(scheme_names)}"

    context = format_chunks_for_llm(all_chunks)
    user_prompt = (
        f"Compare these schemes: {', '.join(scheme_names)}\n\n"
        f"User question: {ctx.user_message}\n\n"
        f"Scheme data:\n{context}"
    )

    reply = ask_llm(COMPARISON_SYSTEM, user_prompt, history=ctx.history)
    if reply:
        return format_for_whatsapp(reply)

    # Fallback: simple list
    lines = [f"⚖️ *Comparing {len(scheme_names)} schemes:*\n"]
    for name in scheme_names:
        scheme_chunks = [c for c in all_chunks if c.scheme_name.lower() == name.lower()]
        if scheme_chunks:
            c = scheme_chunks[0]
            lines.append(
                f"\n*{name}*\n"
                f"• {c.content[:200]}…\n"
                f"🔗 {c.source_url}"
            )
    return format_for_whatsapp("\n".join(lines))


# ------------------------------------------------------------------ LangGraph node


def comparison_node(state: "GovGraphState") -> dict:
    """LangGraph node: side-by-side scheme comparison."""
    from app.agents.graph_utils import agent_context

    return {"reply": run(agent_context(state))}
