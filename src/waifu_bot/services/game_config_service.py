"""Load key/value rows from `game_config` with process-local TTL cache."""
from __future__ import annotations

import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import GameConfig

# Process-local cache (single asyncio worker per deployment is the common case).
_CACHE_TTL_SECONDS = 45.0
_cached_map: dict[str, str] | None = None
_cache_expires_at: float = 0.0


def invalidate_game_config_cache() -> None:
    """Clear in-memory config cache (e.g. after admin KV update)."""
    global _cached_map, _cache_expires_at
    _cached_map = None
    _cache_expires_at = 0.0


async def get_game_config_map(session: AsyncSession) -> dict[str, str]:
    global _cached_map, _cache_expires_at
    now = time.monotonic()
    if _cached_map is not None and now < _cache_expires_at:
        return dict(_cached_map)
    rows = (await session.execute(select(GameConfig))).scalars().all()
    loaded = {r.key: r.value for r in rows}
    _cached_map = loaded
    _cache_expires_at = now + _CACHE_TTL_SECONDS
    return dict(loaded)


def cfg_float(cfg: dict[str, str], key: str, default: float) -> float:
    try:
        return float(cfg.get(key, default))
    except (TypeError, ValueError):
        return default


def cfg_int(cfg: dict[str, str], key: str, default: int) -> int:
    try:
        return int(float(cfg.get(key, default)))
    except (TypeError, ValueError):
        return default


def cfg_bool(cfg: dict[str, str], key: str, default: bool = False) -> bool:
    raw = cfg.get(key)
    if raw is None:
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")
