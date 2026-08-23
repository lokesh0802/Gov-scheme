from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any
from urllib.parse import urlparse

import requests
from fastapi import HTTPException

from app.core.config import settings
from app.whatsapp.schemas import DEFAULT_WEBHOOK_EVENTS

logger = logging.getLogger(__name__)

# (chat_id, body_prefix) of texts we just sent — used to ignore OpenWA echoes
_outbound: deque[tuple[str, str, float]] = deque(maxlen=200)
_OUTBOUND_TTL = 90.0
_OUTBOUND_PREFIX = 120


def _headers() -> dict[str, str]:
    return {
        "X-API-key": settings.openwa_api_key,
        "Content-Type": "application/json",
    }


def _request(method: str, url: str, payload: dict | None = None, timeout: int = 30) -> Any:
    try:
        response = requests.request(method, url, headers=_headers(), json=payload, timeout=timeout)
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = exc.response.text if exc.response is not None else str(exc)
        status = exc.response.status_code if exc.response is not None else 502
        logger.error("OpenWA %s %s failed: %s", method, url, detail)
        raise HTTPException(status_code=status, detail=f"OpenWA request failed: {detail}") from exc
    except requests.RequestException as exc:
        logger.error("OpenWA %s %s unreachable: %s", method, url, exc)
        raise HTTPException(status_code=502, detail=f"OpenWA unreachable: {exc}") from exc
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text}


def remember_outbound(chat_id: str, text: str) -> None:
    _outbound.append((chat_id, (text or "")[:_OUTBOUND_PREFIX], time.time()))


def is_our_outbound(chat_id: str, text: str) -> bool:
    now = time.time()
    prefix = (text or "")[:_OUTBOUND_PREFIX]
    return any(
        chat == chat_id and body == prefix and now - ts < _OUTBOUND_TTL
        for chat, body, ts in _outbound
    )


def send_text_message(chat_id: str, text: str) -> dict:
    """Send a text message via the connected OpenWA session."""
    remember_outbound(chat_id, text)
    return _request(
        "POST",
        settings.send_text_url,
        {"chatId": chat_id, "text": text},
    )


def register_webhook(url: str, events: list[str], secret: str) -> dict:
    """Tell OpenWA where to deliver webhook events."""
    return _request(
        "POST",
        settings.register_webhook_url,
        {"url": url, "events": events, "secret": secret},
    )


def list_session_webhooks() -> list[dict]:
    result = _request("GET", settings.register_webhook_url, timeout=10)
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        for key in ("data", "webhooks", "items"):
            value = result.get(key)
            if isinstance(value, list):
                return value
    return []


def update_webhook(webhook_id: str, payload: dict) -> dict:
    return _request(
        "PUT",
        f"{settings.register_webhook_url}/{webhook_id}",
        payload,
        timeout=10,
    )


def _urls_match(left: str, right: str) -> bool:
    a, b = urlparse((left or "").rstrip("/")), urlparse((right or "").rstrip("/"))
    return (a.scheme, a.netloc.lower(), a.path.rstrip("/")) == (
        b.scheme,
        b.netloc.lower(),
        b.path.rstrip("/"),
    )


def ensure_inbound_webhook() -> dict | None:
    """
    Make sure OpenWA posts message.received (and message.sent) to this app.

    The dashboard Test button only sends event=test and does not prove real
    chats are subscribed. Missing or incomplete event lists are why 'hi'
    never appears in the FastAPI logs.
    """
    if not settings.session_id or not settings.openwa_api_key:
        logger.warning("Skipping webhook ensure — SESSION_DETAILS_SESSION_ID or API key missing")
        return None

    wanted = list(DEFAULT_WEBHOOK_EVENTS)
    target = settings.webhook_url
    hooks = list_session_webhooks()
    match = next((h for h in hooks if _urls_match(str(h.get("url") or ""), target)), None)

    if match:
        events = [str(e) for e in (match.get("events") or [])]
        active = bool(match.get("active", True))
        missing = [e for e in wanted if e not in events]
        if not missing and active:
            logger.info(
                "OpenWA webhook ok id=%s url=%s events=%s lastTriggeredAt=%s",
                match.get("id"),
                match.get("url"),
                events,
                match.get("lastTriggeredAt"),
            )
            return match
        updated = update_webhook(
            str(match["id"]),
            {"url": target, "events": wanted, "active": True},
        )
        logger.info("Updated OpenWA webhook %s events=%s", match.get("id"), wanted)
        return updated if isinstance(updated, dict) else match

    created = register_webhook(target, wanted, settings.session_secret)
    logger.info("Registered OpenWA webhook url=%s events=%s", target, wanted)
    return created if isinstance(created, dict) else {"url": target, "events": wanted}
