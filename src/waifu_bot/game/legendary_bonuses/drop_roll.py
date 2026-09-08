"""Roll legendary unique bonus ids when a legendary item is generated."""

from __future__ import annotations

import random
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.game.legendary_bonuses.eligibility import bonus_fits_drop, drop_weight_for_bonus
from waifu_bot.game.legendary_bonuses.tier_scale import roll_bonus_magnitudes

_CANDIDATE_CACHE: dict[tuple[int, str], list[dict[str, Any]]] | None = None


async def _load_eligible_bonuses(
    session: AsyncSession,
    *,
    tier: int,
    slot_type: str,
) -> list[dict[str, Any]]:
    global _CANDIDATE_CACHE
    cache_key = (int(tier), str(slot_type).lower())
    if _CANDIDATE_CACHE is not None and cache_key in _CANDIDATE_CACHE:
        return _CANDIDATE_CACHE[cache_key]

    rows = (
        await session.execute(
            text(
                """
                SELECT
                    id,
                    bonus_key,
                    name,
                    description_tpl,
                    trigger_group,
                    params,
                    is_active,
                    min_item_tier,
                    max_item_tier,
                    allowed_slot_types,
                    is_drop_enabled
                FROM legendary_bonuses
                WHERE is_active = TRUE
                  AND is_drop_enabled = TRUE
                  AND min_item_tier <= :tier
                  AND max_item_tier >= :tier
                """
            ),
            {"tier": int(tier)},
        )
    ).mappings().all()

    eligible: list[dict[str, Any]] = []
    for row in rows:
        bonus = dict(row)
        if bonus_fits_drop(bonus, tier=tier, slot_type=slot_type):
            eligible.append(bonus)

    if _CANDIDATE_CACHE is None:
        _CANDIDATE_CACHE = {}
    _CANDIDATE_CACHE[cache_key] = eligible
    return eligible


def clear_drop_roll_cache() -> None:
    """Test helper: reset in-memory candidate cache."""
    global _CANDIDATE_CACHE
    _CANDIDATE_CACHE = None


def pick_bonus_from_candidates(
    candidates: list[dict[str, Any]],
    *,
    tier: int,
    slot_type: str,
) -> dict[str, Any] | None:
    if not candidates:
        return None
    weights = [drop_weight_for_bonus(b, tier=tier, slot_type=slot_type) for b in candidates]
    return random.choices(candidates, weights=weights, k=1)[0]


async def roll_legendary_bonus_ids(
    session: AsyncSession,
    *,
    tier: int,
    slot_type: str,
    item_level: int | None = None,
) -> list[int]:
    """Return exactly one rolled bonus id, or empty if pool is empty."""
    ids, _rolls = await roll_legendary_bonus_bundle(
        session, tier=tier, slot_type=slot_type, item_level=item_level
    )
    return ids


async def roll_legendary_bonus_bundle(
    session: AsyncSession,
    *,
    tier: int,
    slot_type: str,
    item_level: int | None = None,
    midpoint: bool = False,
) -> tuple[list[int], dict[str, dict]]:
    """Return (bonus ids, magnitude overlay keyed by bonus id string)."""
    _ = item_level
    candidates = await _load_eligible_bonuses(session, tier=tier, slot_type=slot_type)
    picked = pick_bonus_from_candidates(candidates, tier=tier, slot_type=slot_type)
    if picked is None:
        return [], {}
    bid = int(picked["id"])
    overlay = roll_bonus_magnitudes(picked.get("params") or {}, int(tier), midpoint=midpoint)
    return [bid], {str(bid): overlay}
