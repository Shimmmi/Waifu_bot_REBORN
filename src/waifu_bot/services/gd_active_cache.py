"""Redis cache for active GD v1 cycle per group chat (reduces hot-path SELECTs)."""
from __future__ import annotations

import json
import logging
from typing import Any

from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

REDIS_GD_V1_ACTIVE_PREFIX = "gd_v1_active:"
CACHE_TTL_SECONDS = 45
SENTINEL_NONE = "none"


def _key(chat_id: int) -> str:
    return f"{REDIS_GD_V1_ACTIVE_PREFIX}{int(chat_id)}"


async def get_cached_active_cycle_id(redis: Any, chat_id: int) -> int | None | bool:
    """
    Return cycle_id (int), None if chat has no active cycle (cached negative),
    or False if cache miss (caller should query DB).
    """
    if redis is None:
        return False
    try:
        raw = await redis.get(_key(chat_id))
    except RedisError:
        logger.debug("gd_active_cache get failed chat_id=%s", chat_id, exc_info=True)
        return False
    if raw is None:
        return False
    text = raw.decode() if isinstance(raw, bytes) else str(raw)
    if text == SENTINEL_NONE:
        return None
    try:
        data = json.loads(text)
        cid = data.get("cycle_id")
        return int(cid) if cid is not None else None
    except (json.JSONDecodeError, TypeError, ValueError):
        return False


async def set_active_cycle_cache(
    redis: Any, chat_id: int, cycle_id: int | None, *, ttl: int = CACHE_TTL_SECONDS
) -> None:
    if redis is None:
        return
    payload = SENTINEL_NONE if cycle_id is None else json.dumps({"cycle_id": int(cycle_id)})
    try:
        await redis.set(_key(chat_id), payload, ex=max(1, int(ttl)))
    except RedisError:
        logger.debug("gd_active_cache set failed chat_id=%s", chat_id, exc_info=True)


async def invalidate_active_cycle_cache(redis: Any, chat_id: int) -> None:
    if redis is None:
        return
    try:
        await redis.delete(_key(chat_id))
    except RedisError:
        logger.debug("gd_active_cache delete failed chat_id=%s", chat_id, exc_info=True)
