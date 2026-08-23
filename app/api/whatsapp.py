from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings
from app.whatsapp import ensure_inbound_webhook, list_session_webhooks, register_webhook, send_text_message
from app.whatsapp.schemas import RegisterWebhookRequest, SendTextMessageRequest

router = APIRouter(tags=["whatsapp"])


@router.get("/webhooks")
async def list_webhooks_endpoint():
    """Show OpenWA webhooks for this session (event list, lastTriggeredAt)."""
    return {
        "sessionId": settings.session_id,
        "webhookUrl": settings.webhook_url,
        "webhooks": list_session_webhooks(),
    }


@router.post("/webhooks/register")
async def register_webhook_endpoint(body: RegisterWebhookRequest = RegisterWebhookRequest()):
    """Register this app's webhook URL with OpenWA. Empty body uses .env defaults."""
    secret = body.secret or settings.session_secret
    if body.url == settings.webhook_url and body.events:
        return ensure_inbound_webhook() or register_webhook(body.url, body.events, secret)
    return register_webhook(body.url, body.events, secret)


@router.post("/messages/send-text")
async def send_text_message_endpoint(body: SendTextMessageRequest):
    """Manually send a text message (useful for testing)."""
    return send_text_message(body.chatId, body.text)
