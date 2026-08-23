"""
Response Agent — generates the final WhatsApp reply.

RULE: Only use text from retrieved chunks. Never invent facts.
"""

from __future__ import annotations

import logging

from app.agents.llm import ask_llm
from app.agents.prompts import NO_API_KEY, NO_RESULTS, RESPONSE_SYSTEM
from app.agents.retrieval import format_chunks_for_llm
from app.agents.scheme_list import unique_schemes_ordered
from app.agents.types import AgentContext
from app.core.config import settings
from app.whatsapp.formatting import format_for_whatsapp, format_search_list

logger = logging.getLogger(__name__)


def run(ctx: AgentContext) -> str:
    if not ctx.chunks:
        return NO_RESULTS

    context = format_chunks_for_llm(ctx.chunks)
    user_prompt = (
        f"User question: {ctx.user_message}\n\n"
        f"Context from government scheme database:\n{context}"
    )

    reply = ask_llm(RESPONSE_SYSTEM, user_prompt, history=ctx.history)
    if reply:
        return format_for_whatsapp(reply)

    if not settings.openai_api_key:
        return NO_API_KEY + "\n\n" + _fallback(ctx)

    return _fallback(ctx)


def run_scheme_detail(scheme_name: str, chunks: list) -> str:
    """Full details for one scheme (after user picks 1, 2, 3…)."""
    if not chunks:
        return NO_RESULTS

    context = format_chunks_for_llm(chunks)
    user_prompt = (
        f"Give full details about the scheme: {scheme_name}\n\n"
        f"Include: what it is, benefits, eligibility, documents, how to apply.\n\n"
        f"Scheme data:\n{context}"
    )

    reply = ask_llm(RESPONSE_SYSTEM, user_prompt, max_tokens=900)
    if reply:
        return format_for_whatsapp(reply)

    chunk = chunks[0]
    return format_for_whatsapp(
        f"*{scheme_name}*\n"
        f"📍 {chunk.level} | {chunk.state}\n\n"
        f"{chunk.content[:500]}…\n\n"
        f"🔗 {chunk.source_url}\n\n"
        f"Ask about *eligibility* or *how to apply* for this scheme."
    )


def run_search_results(ctx: AgentContext) -> str:
    """Format search results as a numbered list — order matches last_search_slugs."""
    if not ctx.chunks:
        return NO_RESULTS

    schemes = []
    for chunk in unique_schemes_ordered(ctx.chunks)[:4]:
        summary = chunk.content
        if chunk.section not in ("description", "benefits"):
            for c in ctx.chunks:
                if c.slug == chunk.slug and c.section in ("description", "benefits"):
                    summary = c.content
                    break
        schemes.append({
            "name": chunk.scheme_name,
            "category": chunk.category,
            "level": chunk.level,
            "state": chunk.state,
            "summary": summary[:200],
            "url": chunk.source_url,
        })

    return format_search_list(schemes)


def _fallback(ctx: AgentContext) -> str:
    """Plain-text answer when LLM is unavailable."""
    blocks = []
    for chunk in unique_schemes_ordered(ctx.chunks)[:3]:
        blocks.append(
            f"*{len(blocks) + 1}. {chunk.scheme_name}*\n"
            f"📍 {chunk.level} | {chunk.state}\n"
            f"{chunk.content[:250]}…\n"
            f"🔗 {chunk.source_url}"
        )

    if not blocks:
        return NO_RESULTS

    header = f"✅ *Found {len(blocks)} scheme(s):*\n\n"
    footer = "\n\n👆 Reply *1*, *2*, *3* for full details."
    return header + "\n\n".join(blocks) + footer


def _apply_search_slugs(state: "GovGraphState", ctx: AgentContext) -> str:
    """Format numbered list and persist slug order on conversation."""
    conv = state["conversation"]
    ordered = unique_schemes_ordered(ctx.chunks)
    conv.last_search_slugs = [c.slug for c in ordered]
    conv.active_scheme_slug = None
    return run_search_results(ctx)


# ------------------------------------------------------------------ LangGraph nodes


def search_list_node(state: "GovGraphState") -> dict:
    from app.agents.graph_utils import agent_context

    return {"reply": _apply_search_slugs(state, agent_context(state))}


def detail_branch_node(state: "GovGraphState") -> dict:
    from app.agents.graph_utils import agent_context

    ctx = agent_context(state)
    ordered = unique_schemes_ordered(ctx.chunks)
    if len(ordered) > 1:
        return {"reply": _apply_search_slugs(state, ctx)}
    conv = state["conversation"]
    if ctx.chunks:
        conv.active_scheme_slug = ctx.chunks[0].slug
    return {"reply": run(ctx)}


def default_branch_node(state: "GovGraphState") -> dict:
    from app.agents.graph_utils import agent_context

    ctx = agent_context(state)
    if len(unique_schemes_ordered(ctx.chunks)) > 1:
        return {"reply": _apply_search_slugs(state, ctx)}
    return {"reply": run(ctx)}


def select_node(state: "GovGraphState") -> dict:
    """LangGraph node: user picked 1 / 2 / 3 from a scheme list."""
    import logging

    from app.agents.graph_state import GovGraphState
    from app.agents.graph_utils import save_static_reply, split_reply
    from app.agents.prompts import NO_INDEX
    from app.agents.retrieval import retrieve_for_slug
    from app.agents.scheme_list import pending_search_slugs
    from app.rag.vector_store import vector_store
    from app.storage.conversations import save_conversation

    log = logging.getLogger(__name__)
    text = state["user_message"]
    conv = state["conversation"]

    try:
        index = int(text.strip()) - 1
    except ValueError:
        return save_static_reply(state, "Please reply with a number from the list (e.g. 1, 2, 3).")

    slugs = pending_search_slugs(conv.last_search_slugs, conv.messages)
    if not slugs or index < 0 or index >= len(slugs):
        return save_static_reply(state, "That number is not in the list. Please search again.")

    slug = slugs[index]
    conv.last_search_slugs = slugs
    conv.active_scheme_slug = slug

    if not vector_store.is_ready:
        return save_static_reply(state, NO_INDEX)

    chunks = retrieve_for_slug(slug)
    if not chunks:
        return save_static_reply(state, "Scheme not found. Please search again.")

    scheme_name = chunks[0].scheme_name
    log.info("User selected #%d → %s (%s)", index + 1, scheme_name, slug)
    reply = run_scheme_detail(scheme_name, chunks)

    conv.add_message("user", text)
    conv.add_message("assistant", reply)
    save_conversation(conv)
    return {
        "reply": reply,
        "parts": split_reply(reply),
        "conversation_saved": True,
    }
