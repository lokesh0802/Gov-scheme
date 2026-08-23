from __future__ import annotations

import logging
from typing import Any

from app.agents.orchestrator import orchestrator
from app.agents.router import status_while_processing
from app.core.config import settings
from app.storage.conversations import get_conversation
from app.whatsapp.client import is_our_outbound, send_text_message
from app.whatsapp.formatting import unwrap_whatsapp_transcript
from app.whatsapp.schemas import (
    IGNORE_EVENT_NAMES,
    INCOMING_EVENT_NAMES,
    LINKED_DEVICE_EVENT_NAMES,
    WebhookEvent,
)

logger = logging.getLogger(__name__)

# If OpenWA echoes a send as message.sent with slightly different text, still skip it
_BOT_REPLY_PREFIXES = (
    "👋 *Namaste!",
    "Welcome back!",
    "🔍 Searching",
    "📋 Fetching",
    "📋 Loading",
    "✅ Checking",
    "⚖️ Comparing",
    "📝 Looking up",
    "*GovScheme Assistant",
    "✅ *Found",
    "I couldn't find schemes",
    "⚠️ Search is not ready",
    "⚠️ AI replies need",
)


def _normalize_phone(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    if digits.startswith("91") and len(digits) > 10:
        return digits[2:]
    return digits


def _looks_like_phone_jid(value: str) -> bool:
    text = (value or "").lower()
    if "@lid" in text or "@g.us" in text or "@newsletter" in text or "@broadcast" in text:
        return False
    digits = "".join(ch for ch in value if ch.isdigit())
    return "@c.us" in text or 10 <= len(digits) <= 15


def _addressed_to_bot(event: WebhookEvent) -> bool:
    """Only drop when 'to' is clearly a different phone number than the bot."""
    if not event.data or not event.data.to:
        return True
    dest = event.data.to
    if not _looks_like_phone_jid(dest):
        return True
    bot = _normalize_phone(settings.bot_phone_number)
    dest_digits = _normalize_phone(dest)
    return not bot or dest_digits == bot


def _should_handle(event: WebhookEvent) -> tuple[bool, str]:
    if event.event in IGNORE_EVENT_NAMES:
        return False, f"event:{event.event}"

    handleable = event.event in INCOMING_EVENT_NAMES | LINKED_DEVICE_EVENT_NAMES
    if not handleable:
        return False, f"unhandled_event:{event.event}"

    if event.is_channel_or_status:
        return False, "not_direct_chat"

    if not event.chat_id:
        return False, "no_chat_id"

    linked = event.from_me or event.event in LINKED_DEVICE_EVENT_NAMES
    # message.sent puts the other person in `to` — do not require it to be the bot number
    if not linked and not _addressed_to_bot(event):
        return False, "not_for_bot"

    if linked:
        body = event.user_text or ""
        if is_our_outbound(event.chat_id, body):
            return False, "outbound_echo"
        if any(body.startswith(prefix) for prefix in _BOT_REPLY_PREFIXES):
            return False, "outbound_echo"
        if event.is_group:
            return False, "group_from_me"
        if not event.is_direct_chat:
            return False, "linked_device_not_dm"
        return True, "linked_device"

    return True, "incoming"


def handle_webhook_event(payload: dict[str, Any]) -> dict:
    """
    Process an incoming OpenWA webhook event.

    Flow:
      1. Parse payload
      2. Ignore non-user messages
      3. Send instant status message if the reply will take a few seconds
      4. Run multi-agent RAG pipeline on user text
      5. Send reply (split if longer than 4000 chars)
    """
    event = WebhookEvent.from_payload(payload)
    user_text = unwrap_whatsapp_transcript(event.user_text)
    body_preview = user_text.replace("\n", " ")[:80]
    logger.info(
        "Webhook event=%s session=%s chatId=%s fromMe=%s body=%r",
        event.event,
        event.sessionId,
        event.chat_id,
        event.from_me,
        body_preview,
    )

    handle, reason = _should_handle(event)
    if not handle:
        logger.info(
            "Ignoring webhook event=%s reason=%s chatId=%s body=%r",
            event.event,
            reason,
            event.chat_id,
            body_preview,
        )
        return {"ok": True, "action": "ignored", "reason": reason, "event": event.event}

    chat_id = event.chat_id
    if not user_text:
        logger.info("Skipping empty body chat=%s type=%s", chat_id, event.data.type if event.data else None)
        return {"ok": True, "action": "skipped", "reason": "empty_body", "chatId": chat_id}

    logger.info("Handling user text chat=%s via=%s body=%r", chat_id, reason, body_preview)

    try:
        status = status_while_processing(user_text, get_conversation(chat_id))
        if status:
            try:
                send_text_message(chat_id, status)
                logger.info("Status sent to %s: %s", chat_id, status[:40])
            except Exception:
                logger.warning("Could not send status message to %s", chat_id, exc_info=True)

        replies = orchestrator.process(chat_id, user_text)
        if not replies:
            logger.warning("Orchestrator returned no reply for %s body=%r", chat_id, body_preview)
            return {"ok": True, "action": "no_reply", "chatId": chat_id}

        for part in replies:
            send_text_message(chat_id, part)
            logger.info("Replied to %s (%d chars) sent=yes", chat_id, len(part))
        return {
            "ok": True,
            "action": "replied",
            "chatId": chat_id,
            "parts": len(replies),
            "via": reason,
        }
    except Exception as exc:
        logger.exception("Failed to reply to %s: %s", chat_id, exc)
        return {"ok": True, "action": "reply_failed", "chatId": chat_id, "error": str(exc)}
