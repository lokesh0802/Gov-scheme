from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from app.whatsapp.handler import handle_webhook_event

router = APIRouter(tags=["webhook"])
logger = logging.getLogger(__name__)


@router.post("/webhook")
async def receive_webhook(request: Request):
    """OpenWA delivers events here. Register: http://127.0.0.1:8000/webhook"""
    try:
        payload = await request.json()
    except Exception:
        raw = await request.body()
        logger.exception("Webhook body is not JSON (%d bytes)", len(raw))
        return {"ok": False, "action": "invalid_json"}

    event_name = payload.get("event") if isinstance(payload, dict) else None
    data = payload.get("data") if isinstance(payload, dict) else None
    body = ""
    if isinstance(data, dict):
        body = str(data.get("body") or data.get("text") or data.get("message") or "")
    elif isinstance(data, str):
        body = data
    logger.info(
        "Webhook POST event=%s keys=%s body=%r",
        event_name,
        list(payload) if isinstance(payload, dict) else type(payload).__name__,
        body.replace("\n", " ")[:80],
    )
    try:
        return handle_webhook_event(payload if isinstance(payload, dict) else {})
    except Exception:
        logger.exception("Webhook handler crashed event=%s", event_name)
        return {"ok": True, "action": "handler_error", "event": event_name}
