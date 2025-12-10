"""Redis client helper."""
from redis import asyncio as aioredis

from waifu_bot.core.config import settings

_redis = None


def get_redis():
    """Lazy init and return Redis client."""
    global _redis  # noqa: PLW0603
    if _redis is None:
        _redis = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis

