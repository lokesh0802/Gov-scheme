"""
Eligibility Agent — checks if a user qualifies for a scheme.

Steps:
  1. Retrieve eligibility chunks from Chroma
  2. Compare against user profile (state, age, category, …)
  3. Return a clear eligible / not eligible explanation
"""

from __future__ import annotations

import logging

from app.agents.llm import ask_llm
from app.agents.prompts import ELIGIBILITY_SYSTEM
from app.agents.retrieval import format_chunks_for_llm
from app.agents.types import AgentContext
from app.storage.conversations import UserProfile
from app.whatsapp.formatting import format_for_whatsapp

logger = logging.getLogger(__name__)


def run(ctx: AgentContext) -> str:
    eligibility_chunks = [c for c in ctx.chunks if c.section == "eligibility"] or ctx.chunks

    if not eligibility_chunks:
        return (
            "I couldn't find eligibility information for that scheme. "
            "Try searching for the scheme first, then ask about eligibility."
        )

    context = format_chunks_for_llm(eligibility_chunks)
    profile = _profile_text(ctx.user_profile)

    user_prompt = (
        f"User question: {ctx.user_message}\n\n"
        f"User profile:\n{profile}\n\n"
        f"Eligibility information from database:\n{context}"
    )

    reply = ask_llm(ELIGIBILITY_SYSTEM, user_prompt, history=ctx.history)
    if reply:
        return format_for_whatsapp(reply)

    # Fallback without LLM
    chunk = eligibility_chunks[0]
    return format_for_whatsapp(
        f"*Eligibility — {chunk.scheme_name}*\n\n"
        f"{chunk.content[:600]}\n\n"
        f"🔗 {chunk.source_url}\n\n"
        f"_This is guidance only. Confirm on the official website._"
    )


def _profile_text(profile: dict) -> str:
    if not profile or not any(profile.values()):
        return "No profile set yet. Ask the user for: state, age, gender, category (SC/ST/OBC/General), occupation."
    lines = [f"  {k}: {v}" for k, v in profile.items() if v]
    return "\n".join(lines) or "No profile set."


def update_profile_from_message(profile: UserProfile, message: str) -> UserProfile:
    """Try to extract profile fields from the user's message."""
    text = message.lower()

    for state in [
        "karnataka", "tamil nadu", "maharashtra", "kerala", "delhi",
        "uttar pradesh", "gujarat", "rajasthan", "west bengal", "bihar",
    ]:
        if state in text:
            profile.state = state.title()

    for cat in ["sc", "st", "obc", "general", "ews"]:
        if f" {cat} " in f" {text} " or text.startswith(cat):
            profile.category = cat.upper()

    if "female" in text or "woman" in text:
        profile.gender = "female"
    elif "male" in text:
        profile.gender = "male"

    for occ in ["student", "farmer", "entrepreneur", "unemployed", "worker"]:
        if occ in text:
            profile.occupation = occ

    # Extract age: "I am 22" or "age 22"
    import re
    age_match = re.search(r"\b(?:age|i am|i'm)\s*(\d{2})\b", text)
    if age_match:
        profile.age = int(age_match.group(1))

    return profile


# ------------------------------------------------------------------ LangGraph node


def eligibility_node(state: "GovGraphState") -> dict:
    """LangGraph node: check user eligibility against scheme rules."""
    from app.agents.graph_utils import agent_context

    conv = state["conversation"]
    ctx = agent_context(state)
    conv.user_profile = update_profile_from_message(conv.user_profile, ctx.user_message)
    return {"reply": run(ctx)}
