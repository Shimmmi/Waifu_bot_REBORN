"""Solo dungeon completion chest: DropRule + Magic Find, plus-scaled rolls."""

from __future__ import annotations

import logging
import random
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import DropRule
from waifu_bot.game.constants import MAX_LEVEL
from waifu_bot.game.dungeon_plus_scaling import (
    apply_completion_rarity_floor,
    dungeon_plus_completion_item_level,
    dungeon_plus_completion_item_rolls,
    dungeon_plus_drop_effective_act,
)
from waifu_bot.game.formulas import blend_rarity_weights_with_magic_find
from waifu_bot.services.item_service import ItemService

logger = logging.getLogger(__name__)

_FALLBACK_RARITY_WEIGHTS: list[tuple[int, int]] = [(1, 70), (2, 25), (3, 5)]


def parse_drop_rule_weights(weights: Any) -> list[tuple[int, int]]:
    opts: list[tuple[int, int]] = []
    if isinstance(weights, dict):
        for k, w in weights.items():
            try:
                rk = int(k)
                ww = int(w)
            except (TypeError, ValueError):
                continue
            if ww > 0:
                opts.append((rk, ww))
    return opts or list(_FALLBACK_RARITY_WEIGHTS)


def pick_weighted_rarity(opts: list[tuple[int, int]], rng: random.Random | None = None) -> int:
    pool = opts or list(_FALLBACK_RARITY_WEIGHTS)
    total_w = sum(int(w) for _, w in pool)
    if total_w <= 0:
        return 1
    roller = rng.randint if rng is not None else random.randint
    roll = roller(1, total_w)
    acc = 0
    rarity = 1
    for r, w in pool:
        acc += int(w)
        if roll <= acc:
            return int(r)
    return int(pool[-1][0])


def cap_plus_item_equip_level(inv: Any) -> None:
    """Keep plus-item power (ilvl) but do not lock equip behind waifu.level > MAX_LEVEL."""
    cap = int(MAX_LEVEL)
    req = getattr(inv, "requirements", None)
    if isinstance(req, dict):
        need = int(req.get("level") or 0)
        if need > cap:
            patched = dict(req)
            patched["level"] = cap
            inv.requirements = patched
    item = getattr(inv, "item", None)
    if item is not None and int(getattr(item, "required_level", 0) or 0) > cap:
        item.required_level = cap


def inventory_item_drop_payload(inv: Any, *, rarity: int, item_level: int) -> dict[str, Any]:
    item_display_name = (
        getattr(inv, "_display_name", None)
        or (inv.item.name if getattr(inv, "item", None) else None)
        or "Предмет"
    )
    return {
        "inventory_item_id": inv.id,
        "name": item_display_name,
        "rarity": int(inv.rarity or rarity),
        "level": int(inv.level or item_level),
        "tier": int(inv.tier or 1),
        "slot_type": getattr(inv, "slot_type", None),
    }


async def load_drop_rule_weight_opts(session: AsyncSession, act: int) -> list[tuple[int, int]]:
    rule_q = await session.execute(
        select(DropRule).where(DropRule.act == int(act), DropRule.boss_only == True)  # noqa: E712
    )
    rule = rule_q.scalar_one_or_none()
    weights = getattr(rule, "rarity_weights", None) or {} if rule else {}
    return parse_drop_rule_weights(weights)


async def grant_solo_completion_items(
    session: AsyncSession,
    *,
    item_service: ItemService,
    player_id: int,
    dungeon: Any,
    plus_level: int,
    total_mf_pct: float,
    drop_power_rank: int = 0,
    economy: str | None = None,
) -> list[dict[str, Any]]:
    """Grant 1+ completion items. Failures are logged; remaining rolls still attempt."""
    pl = max(0, int(plus_level or 0))
    dungeon_act = int(getattr(dungeon, "act", 1) or 1)
    effective_act = dungeon_plus_drop_effective_act(dungeon_act, pl)
    rolls = dungeon_plus_completion_item_rolls(pl)
    rank = int(drop_power_rank or 0)
    dungeon_level = int(getattr(dungeon, "level", 1) or 1)

    try:
        opts = await load_drop_rule_weight_opts(session, effective_act)
        opts = blend_rarity_weights_with_magic_find(opts, float(total_mf_pct or 0.0))
    except Exception:
        logger.exception(
            "solo completion DropRule load failed player_id=%s act=%s plus=%s",
            player_id,
            effective_act,
            pl,
        )
        opts = list(_FALLBACK_RARITY_WEIGHTS)

    payloads: list[dict[str, Any]] = []
    from waifu_bot.services.item_codex import encounter_item_codex

    for idx in range(rolls):
        try:
            rolled = pick_weighted_rarity(opts)
            rarity = apply_completion_rarity_floor(rolled, pl, is_main=(idx == 0))
            item_level = dungeon_plus_completion_item_level(
                pl,
                dungeon_level,
                drop_power_rank=rank,
            )
            inv = await item_service.generate_inventory_item(
                session=session,
                player_id=player_id,
                act=dungeon_act,
                rarity=rarity,
                level=item_level,
                is_shop=False,
                plus_level=pl,
            )
            if rank > 0:
                inv.power_rank = rank
            elif pl > 0:
                inv.power_rank = int(item_level)
            if pl > 0:
                cap_plus_item_equip_level(inv)
            if economy:
                inv.economy = economy
            await encounter_item_codex(session, int(player_id), inv)
            await session.flush()
            payloads.append(inventory_item_drop_payload(inv, rarity=rarity, item_level=item_level))
        except Exception:
            logger.exception(
                "solo completion loot failed player_id=%s plus=%s roll=%s/%s",
                player_id,
                pl,
                idx + 1,
                rolls,
            )
    return payloads
