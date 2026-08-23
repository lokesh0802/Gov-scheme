from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from app.core.config import settings


INCOMING_EVENT_NAMES = {
    "message.received",
    "message",
    "onMessage",
    "incoming",
    "messages.upsert",
}
# Typed on the linked WhatsApp (OpenWA does not emit message.received for these)
LINKED_DEVICE_EVENT_NAMES = {
    "message.sent",
}
IGNORE_EVENT_NAMES = {
    "test",
    "message.ack",
    "message.failed",
    "session.status",
    "session.qr",
    "session.authenticated",
    "session.disconnected",
}

DEFAULT_WEBHOOK_EVENTS = ["message.received", "message.sent"]


# --- API request bodies (your FastAPI endpoints) ---


class RegisterWebhookRequest(BaseModel):
    url: str = Field(
        default_factory=lambda: settings.webhook_url,
        description="Webhook URL OpenWA will POST events to (use 127.0.0.1, not localhost)",
    )
    events: list[str] = Field(default_factory=lambda: list(DEFAULT_WEBHOOK_EVENTS))
    secret: str = Field(
        default_factory=lambda: settings.session_secret,
        description="Defaults to SESSION_DETAILS_SECRET from .env",
    )


class SendTextMessageRequest(BaseModel):
    chatId: str = Field(
        ...,
        description="WhatsApp chat ID, e.g. 918901975539@c.us",
        examples=["918901975539@c.us"],
    )
    text: str


# --- OpenWA webhook payload (what OpenWA sends to POST /webhook) ---


def _as_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_bool(value: Any) -> Optional[bool]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return None


class IncomingMessageData(BaseModel):
    id: Optional[str] = None
    from_: Optional[str] = Field(default=None, alias="from")
    to: Optional[str] = None
    chatId: Optional[str] = None
    body: Optional[str] = None
    text: Optional[str] = None
    caption: Optional[str] = None
    type: Optional[str] = None
    author: Optional[str] = None
    fromMe: Optional[bool] = None
    isGroup: Optional[bool] = None

    model_config = {"populate_by_name": True, "extra": "ignore"}

    @property
    def user_text(self) -> str:
        for value in (self.body, self.text, self.caption):
            if value and str(value).strip():
                return str(value).strip()
        return ""


class WebhookEvent(BaseModel):
    event: str
    sessionId: Optional[str] = None
    data: Optional[IncomingMessageData] = None

    model_config = {"extra": "ignore"}

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "WebhookEvent":
        raw = payload if isinstance(payload, dict) else {}
        data = raw.get("data")
        if isinstance(data, str):
            data = {"body": data}
        elif isinstance(data, dict):
            data = dict(data)
            nested = data.get("message")
            if isinstance(nested, dict):
                merged = dict(nested)
                merged.update({k: v for k, v in data.items() if k != "message"})
                data = merged
            elif isinstance(nested, str) and not data.get("body"):
                data["body"] = nested
        else:
            data = {}

        try:
            parsed = IncomingMessageData.model_validate(data) if data else None
        except Exception:
            parsed = IncomingMessageData.model_construct(
                id=_as_str(data.get("id")),
                from_=_as_str(data.get("from") or data.get("author")),
                to=_as_str(data.get("to")),
                chatId=_as_str(data.get("chatId") or data.get("chat_id")),
                body=_as_str(data.get("body") or data.get("text") or data.get("caption")),
                type=_as_str(data.get("type")),
                author=_as_str(data.get("author")),
                fromMe=_as_bool(data.get("fromMe")),
                isGroup=_as_bool(data.get("isGroup")),
            )

        return cls(
            event=str(raw.get("event") or raw.get("type") or "unknown"),
            sessionId=_as_str(raw.get("sessionId") or raw.get("session_id")),
            data=parsed,
        )

    @property
    def chat_id(self) -> Optional[str]:
        if not self.data:
            return None
        return self.data.chatId or self.data.from_ or self.data.author

    @property
    def user_text(self) -> str:
        return self.data.user_text if self.data else ""

    @property
    def from_me(self) -> bool:
        return bool(self.data and self.data.fromMe is True)

    @property
    def is_group(self) -> bool:
        chat = self.chat_id or ""
        return bool(self.data and self.data.isGroup) or chat.endswith("@g.us")

    @property
    def is_channel_or_status(self) -> bool:
        chat = self.chat_id or ""
        return chat.endswith("@newsletter") or chat.endswith("@broadcast")

    @property
    def is_direct_chat(self) -> bool:
        chat = self.chat_id or ""
        return chat.endswith("@c.us") or chat.endswith("@lid")

    @property
    def is_incoming_user_message(self) -> bool:
        return self.event in INCOMING_EVENT_NAMES and not self.from_me


# --- Local session storage ---


class WhatsAppSession(BaseModel):
    id: str
    name: str
    status: str
    phone: Optional[str] = None
    pushName: Optional[str] = None
    config: dict = Field(default_factory=dict)
    proxyUrl: Optional[str] = None
    proxyType: Optional[str] = None
    connectedAt: Optional[str] = None
    lastActiveAt: Optional[str] = None
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None
