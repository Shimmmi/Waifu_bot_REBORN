"""Bestiary (pokedex) service: kill tracking, discovery progress, combat bonuses.

This module owns all reads/writes to ``player_monster_codex`` and translates a
player's kill count for a monster template into:

* a discovery tier + reveal flags (what info to show),
* per-monster combat bonuses (damage / damage taken / exp / gold).

Bonuses are *per-monster* (Monster Hunter style): they only apply while fighting
that specific template. Tier lookups during combat are cached in Redis for a
short TTL to avoid a DB round-trip on every message hit.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models.dungeon import PlayerMonsterCodex
from waifu_bot.game import bestiary as bcfg

_CACHE_TTL_SECONDS = 60
_CACHE_PREFIX = "bestiary:tier"


def _cache_key(player_id: int, template_id: int) -> str:
    return f"{_CACHE_PREFIX}:{int(player_id)}:{int(template_id)}"


async def get_kills(session: AsyncSession, player_id: int, template_id: int) -> int:
    """Return the player's logged kills for a monster template (0 if none)."""
    if not template_id:
        return 0
    row = await session.get(PlayerMonsterCodex, (int(player_id), int(template_id)))
    return int(row.kills) if row is not None else 0


async def mark_seen(
    session: AsyncSession, player_id: int, template_id: int | None
) -> None:
    """Ensure a codex row exists for (player, template) without changing kills.

    Used on first contact so the monster shows up as "encountered" (tier 0) even
    before the first kill. No-op for monsters without a template id.
    """
    if not template_id:
        return
    stmt = (
        pg_insert(PlayerMonsterCodex)
        .values(
            player_id=int(player_id),
            monster_template_id=int(template_id),
            kills=0,
            first_seen_at=datetime.utcnow(),
        )
        .on_conflict_do_nothing(index_elements=["player_id", "monster_template_id"])
    )
    await session.execute(stmt)


async def record_kill(
    session: AsyncSession,
    player_id: int,
    template_id: int | None,
    redis=None,
) -> int | None:
    """Increment the kill count for (player, template). Returns the new tier.

    Upserts the codex row, bumps ``kills`` and timestamps, and invalidates the
    Redis tier cache. No-op (returns None) for monsters without a template id.
    """
    if not template_id:
        return None
    now = datetime.utcnow()
    stmt = (
        pg_insert(PlayerMonsterCodex)
        .values(
            player_id=int(player_id),
            monster_template_id=int(template_id),
            kills=1,
            first_seen_at=now,
            first_kill_at=now,
            last_kill_at=now,
        )
        .on_conflict_do_update(
            index_elements=["player_id", "monster_template_id"],
            set_={
                "kills": PlayerMonsterCodex.kills + 1,
                "last_kill_at": now,
                "first_kill_at": func.coalesce(PlayerMonsterCodex.first_kill_at, now),
            },
        )
        .returning(PlayerMonsterCodex.kills)
    )
    new_kills = await session.scalar(stmt)
    if redis is not None:
        try:
            await redis.delete(_cache_key(player_id, template_id))
        except Exception:
            pass
    return bcfg.tier_for_kills(int(new_kills or 0))


async def get_tier(
    session: AsyncSession,
    player_id: int,
    template_id: int | None,
    redis=None,
) -> int:
    """Return the discovery tier for (player, template), with Redis caching."""
    if not template_id:
        return 0
    if redis is not None:
        try:
            cached = await redis.get(_cache_key(player_id, template_id))
            if cached is not None:
                return int(cached)
        except Exception:
            pass
    kills = await get_kills(session, player_id, template_id)
    tier = bcfg.tier_for_kills(kills)
    if redis is not None:
        try:
            await redis.set(_cache_key(player_id, template_id), int(tier), ex=_CACHE_TTL_SECONDS)
        except Exception:
            pass
    return tier


async def get_bestiary_bonuses(
    session: AsyncSession,
    player_id: int,
    template_id: int | None,
    redis=None,
) -> bcfg.BestiaryBonuses:
    """Resolve cumulative per-monster combat bonuses for the current tier."""
    if not template_id:
        return bcfg.BestiaryBonuses()
    tier = await get_tier(session, player_id, template_id, redis=redis)
    return bcfg.cumulative_bonuses_for_tier(tier)
