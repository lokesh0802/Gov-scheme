"""
Per-user conversation memory.

Stored in: data/conversations.json
Keyed by:  WhatsApp chatId

Tracks:
  - message history (for LLM context)
  - active scheme being discussed
  - user profile (for eligibility checks)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

CONVERSATIONS_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "conversations.json"


class ChatMessage(BaseModel):
    role: str       # "user" or "assistant"
    content: str


class UserProfile(BaseModel):
    """Collected gradually for eligibility checks."""
    state: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    category: Optional[str] = None       # SC / ST / OBC / General
    occupation: Optional[str] = None


class ConversationState(BaseModel):
    chat_id: str
    messages: list[ChatMessage] = Field(default_factory=list)
    active_scheme_slug: Optional[str] = None
    last_search_slugs: list[str] = Field(default_factory=list)
    user_profile: UserProfile = Field(default_factory=UserProfile)
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def add_message(self, role: str, content: str) -> None:
        self.messages.append(ChatMessage(role=role, content=content))
        if len(self.messages) > 12:
            self.messages = self.messages[-12:]
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def history(self, last_n: int = 6) -> list[dict[str, str]]:
        return [{"role": m.role, "content": m.content} for m in self.messages[-last_n:]]

    @property
    def is_first_contact(self) -> bool:
        """True if this user has never messaged before."""
        return len(self.messages) == 0


def _read() -> dict:
    CONVERSATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not CONVERSATIONS_FILE.exists():
        CONVERSATIONS_FILE.write_text("{}", encoding="utf-8")
    return json.loads(CONVERSATIONS_FILE.read_text(encoding="utf-8"))


def _write(data: dict) -> None:
    CONVERSATIONS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_conversation(chat_id: str) -> ConversationState:
    data = _read().get(chat_id)
    if data:
        return ConversationState.model_validate(data)
    return ConversationState(chat_id=chat_id)


def save_conversation(state: ConversationState) -> None:
    all_convs = _read()
    state.updated_at = datetime.now(timezone.utc).isoformat()
    all_convs[state.chat_id] = state.model_dump()
    _write(all_convs)
