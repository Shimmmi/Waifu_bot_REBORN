"""Redis flag: player has active solo dungeon run (fast-path for group_message_damage)."""
from __future__ import annotations

import logging
from typing import Any

from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

REDIS_SOLO_ACTIVE_PREFIX = "solo_active:"
CACHE_TTL_SECONDS = 3600
SENTINEL_INACTIVE = "0"
SENTINEL_ACTIVE = "1"


def _key(player_id: int) -> str:
    return f"{REDIS_SOLO_ACTIVE_PREFIX}{int(player_id)}"


async def mark_solo_active(redis: Any, player_id: int, *, ttl: int = CACHE_TTL_SECONDS) -> None:
    if redis is None:
        return
    try:
        await redis.set(_key(player_id), SENTINEL_ACTIVE, ex=max(30, int(ttl)))
    except RedisError:
        logger.debug("solo_active_cache set failed player_id=%s", player_id, exc_info=True)


async def mark_solo_inactive(redis: Any, player_id: int, *, ttl: int = 300) -> None:
    """Negative cache: skip combat/abyss until TTL expires or dungeon starts."""
    if redis is None:
        return
    try:
        await redis.set(_key(player_id), SENTINEL_INACTIVE, ex=max(30, int(ttl)))
    except RedisError:
        logger.debug("solo_active_cache inactive set failed player_id=%s", player_id, exc_info=True)


async def clear_solo_active(redis: Any, player_id: int) -> None:
    if redis is None:
        return
    try:
        await redis.delete(_key(player_id))
    except RedisError:
        logger.debug("solo_active_cache delete failed player_id=%s", player_id, exc_info=True)


async def has_solo_active_cached(redis: Any, player_id: int) -> bool | None:
    """
    Return True if active, False if cached inactive, None on miss or Redis error.
    """
    if redis is None:
        return None
    try:
        raw = await redis.get(_key(player_id))
    except RedisError:
        logger.debug("solo_active_cache get failed player_id=%s", player_id, exc_info=True)
        return None
    if raw is None:
        return None
    text = raw.decode() if isinstance(raw, bytes) else str(raw)
    if text == SENTINEL_ACTIVE:
        return True
    if text == SENTINEL_INACTIVE:
        return False
    return None
