"""
Orchestrator — entry point for the WhatsApp handler.

Delegates to the LangGraph multi-agent workflow (app.agents.graph).
"""

from __future__ import annotations

from app.agents.graph import run_graph, split_reply

WHATSAPP_MAX = 4000


class Orchestrator:
    def process(self, chat_id: str, message: str) -> list[str]:
        """Main entry point. Returns one or more message parts to send."""
        return run_graph(chat_id, message)


def _split(text: str) -> list[str]:
    """Kept for compatibility with tests / imports."""
    return split_reply(text)


orchestrator = Orchestrator()
