"""GD v1: item drops on monster death (solo-style rarity / level)."""
from __future__ import annotations

import logging
import random
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import DropRule
from waifu_bot.services.game_config_service import get_game_config_map, cfg_float
from waifu_bot.services.item_service import ItemService

logger = logging.getLogger(__name__)


def _pick_weighted_pairs(opts: list[tuple[int, float]]) -> int:
    if not opts:
        return 1
    total = sum(max(0.0, w) for _, w in opts)
    if total <= 0:
        return opts[0][0]
    r = random.uniform(0, total)
    acc = 0.0
    for val, w in opts:
        acc += max(0.0, w)
        if r <= acc:
            return val
    return opts[-1][0]


async def _roll_rarity_from_drop_rule(session: AsyncSession, act: int, boss: bool) -> int:
    boss_only = True if boss else False
    q = await session.execute(
        select(DropRule).where(DropRule.act == act, DropRule.boss_only == boss_only)  # noqa: E712
    )
    rule = q.scalar_one_or_none()
    weights = getattr(rule, "rarity_weights", None) or {} if rule else {}
    opts: list[tuple[int, float]] = []
    if isinstance(weights, dict):
        for k, w in weights.items():
            try:
                opts.append((int(k), float(w)))
            except (TypeError, ValueError):
                continue
    if not opts:
        opts = [(1, 70), (2, 25), (3, 5)]
    return _pick_weighted_pairs(opts)


def _act_from_avg_level(avg_level: int) -> int:
    return min(5, max(1, int(avg_level) // 12 + 1))


def pick_loot_recipient_user_id(
    alive_party: list[dict],
    contrib: dict[str, Any],
    *,
    boss: bool,
) -> int | None:
    """Random alive member; boss loot uses equal weight (no damage-based carry)."""
    if not alive_party:
        return None
    return int(random.choice(alive_party)["user_id"])


async def try_award_item_on_monster_kill(
    session: AsyncSession,
    *,
    recipient_user_id: int,
    act: int | None,
    avg_level: int,
    boss: bool,
) -> dict[str, Any] | None:
    """
    Roll drop chance from game_config; generate item into recipient's inventory.
    Returns a summary dict for battle_state loot_awards, or None.
    """
    cfg = await get_game_config_map(session)
    if boss:
        chance = cfg_float(cfg, "gd_item_drop_chance_boss", 1.0)
    else:
        chance = cfg_float(cfg, "gd_item_drop_chance_normal", 0.25)
    if chance < 1.0 and random.random() > chance:
        return None
    act_eff = int(act) if act is not None else _act_from_avg_level(avg_level)
    rarity = await _roll_rarity_from_drop_rule(session, act_eff, boss=boss)
    base_lv = max(1, int(avg_level))
    item_level = max(1, min(base_lv + random.randint(0, 4), 60))
    try:
        svc = ItemService()
        inv = await svc.generate_inventory_item(
            session=session,
            player_id=recipient_user_id,
            act=act_eff,
            rarity=rarity,
            level=item_level,
            is_shop=False,
            plus_level=0,
        )
        await session.flush()
        name = (
            getattr(inv, "_display_name", None)
            or (inv.item.name if getattr(inv, "item", None) else None)
            or "Предмет"
        )
        return {
            "user_id": recipient_user_id,
            "inventory_item_id": inv.id,
            "name": name,
            "rarity": int(inv.rarity or rarity),
            "level": int(inv.level or item_level),
            "tier": int(inv.tier or 1),
            "slot_type": getattr(inv, "slot_type", None),
            "boss": boss,
        }
    except Exception:
        logger.exception("GD loot generation failed uid=%s", recipient_user_id)
        return None


async def distribute_loot(
    session: AsyncSession,
    *,
    party: list[dict[str, Any]],
    contrib: dict[str, Any] | None,
    avg_level: int,
    boss: bool = False,
) -> dict[str, Any] | None:
    """Pick a living party member and try to award a kill drop (public helper for package API)."""
    alive = [p for p in party if not p.get("fallen") and int(p.get("current_hp") or 0) > 0]
    uid = pick_loot_recipient_user_id(alive, contrib or {}, boss=boss)
    if uid is None:
        return None
    return await try_award_item_on_monster_kill(
        session,
        recipient_user_id=uid,
        act=None,
        avg_level=max(1, int(avg_level)),
        boss=boss,
    )
