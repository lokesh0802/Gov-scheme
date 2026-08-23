"""
Skip duplicate webhook deliveries.

OpenWA (or multiple webhook registrations) can deliver the same
message twice. We track processed message IDs for a short window.
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict

logger = logging.getLogger(__name__)

# message_id -> timestamp processed
_seen: OrderedDict[str, float] = OrderedDict()
_TTL_SECONDS = 300   # 5 minutes
_MAX_SIZE = 2000


def is_duplicate(message_id: str | None) -> bool:
    """Return True if this message was already handled recently."""
    if not message_id:
        return False

    now = time.time()
    _evict_expired(now)

    if message_id in _seen:
        logger.info("Duplicate message ignored: %s", message_id)
        return True

    _seen[message_id] = now
    if len(_seen) > _MAX_SIZE:
        _seen.popitem(last=False)
    return False


def _evict_expired(now: float) -> None:
    cutoff = now - _TTL_SECONDS
    while _seen and next(iter(_seen.values())) < cutoff:
        _seen.popitem(last=False)
