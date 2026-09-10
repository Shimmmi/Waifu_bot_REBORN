"""Redis flag: player has an active Abyss session (fast-path for group_message_damage)."""
from __future__ import annotations

import logging
from typing import Any

from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

REDIS_ABYSS_ACTIVE_PREFIX = "abyss_active:"
CACHE_TTL_SECONDS = 3600
SENTINEL_INACTIVE = "0"
SENTINEL_ACTIVE = "1"


def _key(player_id: int) -> str:
    return f"{REDIS_ABYSS_ACTIVE_PREFIX}{int(player_id)}"


async def mark_abyss_active(redis: Any, player_id: int, *, ttl: int = CACHE_TTL_SECONDS) -> None:
    if redis is None:
        return
    try:
        await redis.set(_key(player_id), SENTINEL_ACTIVE, ex=max(30, int(ttl)))
    except RedisError:
        logger.debug("abyss_active_cache set failed player_id=%s", player_id, exc_info=True)


async def mark_abyss_inactive(redis: Any, player_id: int, *, ttl: int = 300) -> None:
    """Negative cache: skip abyss DB lookup until TTL expires or the player enters."""
    if redis is None:
        return
    try:
        await redis.set(_key(player_id), SENTINEL_INACTIVE, ex=max(30, int(ttl)))
    except RedisError:
        logger.debug("abyss_active_cache inactive set failed player_id=%s", player_id, exc_info=True)


async def mark_abyss_inactive_if_missing(redis: Any, player_id: int, *, ttl: int = 300) -> None:
    """Write inactive sentinel only when the key is absent (SET NX)."""
    if redis is None:
        return
    try:
        await redis.set(_key(player_id), SENTINEL_INACTIVE, ex=max(30, int(ttl)), nx=True)
    except TypeError:
        try:
            raw = await redis.get(_key(player_id))
            if raw is None:
                await redis.set(_key(player_id), SENTINEL_INACTIVE, ex=max(30, int(ttl)))
        except RedisError:
            logger.debug("abyss_active_cache nx fallback failed player_id=%s", player_id, exc_info=True)
    except RedisError:
        logger.debug("abyss_active_cache nx set failed player_id=%s", player_id, exc_info=True)


async def has_abyss_active_cached(redis: Any, player_id: int) -> bool | None:
    """Return True if active, False if cached inactive, None on miss or Redis error."""
    if redis is None:
        return None
    try:
        raw = await redis.get(_key(player_id))
    except RedisError:
        logger.debug("abyss_active_cache get failed player_id=%s", player_id, exc_info=True)
        return None
    if raw is None:
        return None
    text = raw.decode() if isinstance(raw, bytes) else str(raw)
    if text == SENTINEL_ACTIVE:
        return True
    if text == SENTINEL_INACTIVE:
        return False
    return None


async def sync_abyss_cache(player_id: int, *, active: bool) -> None:
    try:
        from waifu_bot.core import redis as redis_core

        redis = redis_core.get_redis()
        if active:
            await mark_abyss_active(redis, player_id)
        else:
            await mark_abyss_inactive(redis, player_id)
    except Exception:
        logger.debug("abyss_active_cache sync failed player_id=%s", player_id, exc_info=True)
