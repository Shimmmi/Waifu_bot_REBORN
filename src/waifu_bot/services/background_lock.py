"""Distributed locks for background polling loops (single leader across processes)."""
from __future__ import annotations

import logging
import os
import socket
from typing import Any

from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

_INSTANCE_ID = f"{socket.gethostname()}:{os.getpid()}"
_LOCK_PREFIX = "bg:lock:"


async def try_acquire_background_tick(name: str, ttl_sec: int, redis: Any | None = None) -> bool:
    """
    Acquire a short-lived lock for a background tick name.
    Returns True if this instance should run the tick.
    """
    if redis is None:
        try:
            from waifu_bot.core import redis as redis_core

            redis = redis_core.get_redis()
        except Exception:
            return True
    if redis is None:
        return True
    key = f"{_LOCK_PREFIX}{name}"
    try:
        ok = await redis.set(key, _INSTANCE_ID, nx=True, ex=max(1, int(ttl_sec)))
        return bool(ok)
    except RedisError:
        logger.debug("background lock failed name=%s", name, exc_info=True)
        return True
