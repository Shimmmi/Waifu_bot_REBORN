"""Выдача наград экспедиции v2 по типу reward_type."""
from __future__ import annotations

import logging
import random
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import ActiveExpedition, HiredWaifu, MainWaifu, Player
from waifu_bot.game.constants import (
    EXPEDITION_OUTCOME_FAILURE,
    EXPEDITION_OUTCOME_PARTIAL,
    EXPEDITION_OUTCOME_SUCCESS,
)
from waifu_bot.game.expedition_overhaul import (
    MIXED_REWARD_PENALTY,
    base_reward_amount,
    depth_tier_by_id,
    validate_reward_type,
)
from waifu_bot.services.expedition import OUTCOME_REWARD_MULTIPLIERS, _apply_exp_to_hired_unit

logger = logging.getLogger(__name__)


async def grant_expedition_rewards(
    session: AsyncSession,
    *,
    player: Player,
    active: ActiveExpedition,
    outcome: str,
    squad_ids: list[int],
    player_level: int = 10,
) -> dict[str, Any]:
    """
    Выдать награды по reward_type. Возвращает summary для API:
    gold_gained, exp_gained, waifu_exp_gained, items_earned, enchant_stones, merc_exp_gained.
    """
    rt = validate_reward_type(getattr(active, "reward_type", None)) or "gold"
    depth = depth_tier_by_id(int(getattr(active, "depth_tier", None) or 1))
    if depth is None:
        depth = depth_tier_by_id(1)
    assert depth is not None

    mult = OUTCOME_REWARD_MULTIPLIERS.get(outcome, OUTCOME_REWARD_MULTIPLIERS[EXPEDITION_OUTCOME_FAILURE])
    base = base_reward_amount(rt, depth=depth, player_level=player_level)

    gold_gained = 0
    exp_gained = 0
    waifu_exp_gained = 0
    merc_exp_gained = 0
    enchant_stones = 0
    items_earned: list[dict[str, Any]] = []
    leveled_up_ids: list[int] = []

    if rt == "gold":
        gold_gained = max(0, int(round(base * mult["gold"])))
        player.gold += gold_gained
    elif rt == "waifu_exp":
        waifu_exp_gained = max(0, int(round(base * mult["exp"])))
        mw = await session.scalar(select(MainWaifu).where(MainWaifu.player_id == int(player.id)))
        if mw:
            mw.experience = int(getattr(mw, "experience", 0) or 0) + waifu_exp_gained
            from waifu_bot.services.combat import apply_main_waifu_levelups

            await apply_main_waifu_levelups(session, mw)
        exp_gained = waifu_exp_gained
    elif rt == "merc_exp":
        merc_exp_gained = max(0, int(round(base * mult["exp"] * 1.25)))
        if squad_ids and merc_exp_gained:
            per = max(1, merc_exp_gained // len(squad_ids))
            for wid in squad_ids:
                w = await session.get(HiredWaifu, wid)
                if w and w.player_id == player.id:
                    leveled, _ = _apply_exp_to_hired_unit(w, per)
                    if leveled:
                        leveled_up_ids.append(w.id)
        exp_gained = merc_exp_gained
    elif rt == "enchant":
        if outcome != EXPEDITION_OUTCOME_FAILURE and mult.get("item", False):
            enchant_stones = max(1, int(round(base * mult["gold"])))
            player.protection_stones = int(getattr(player, "protection_stones", 0) or 0) + enchant_stones
        elif outcome == EXPEDITION_OUTCOME_PARTIAL:
            enchant_stones = max(0, int(round(base * 0.5)))
            if enchant_stones:
                player.protection_stones = int(getattr(player, "protection_stones", 0) or 0) + enchant_stones
    elif rt == "items":
        if outcome != EXPEDITION_OUTCOME_FAILURE and mult.get("item", False) and random.random() < 0.85:
            item = await _roll_expedition_item(session, int(player.id), player_level, depth.tier)
            if item:
                items_earned.append(item)
    elif rt == "mixed":
        part = MIXED_REWARD_PENALTY
        gold_gained = max(0, int(round(base * mult["gold"] * part)))
        player.gold += gold_gained
        waifu_exp_gained = max(0, int(round(base * mult["exp"] * part * 0.6)))
        mw = await session.scalar(select(MainWaifu).where(MainWaifu.player_id == int(player.id)))
        if mw and waifu_exp_gained:
            mw.experience = int(getattr(mw, "experience", 0) or 0) + waifu_exp_gained
            from waifu_bot.services.combat import apply_main_waifu_levelups

            await apply_main_waifu_levelups(session, mw)
        per = 0
        if squad_ids:
            per = max(1, int(round(base * mult["exp"] * part * 0.4)) // len(squad_ids))
            for wid in squad_ids:
                w = await session.get(HiredWaifu, wid)
                if w and w.player_id == player.id:
                    leveled, _ = _apply_exp_to_hired_unit(w, per)
                    if leveled:
                        leveled_up_ids.append(w.id)
        merc_exp_gained = per * len(squad_ids) if squad_ids else 0
        exp_gained = waifu_exp_gained + merc_exp_gained
        if outcome != EXPEDITION_OUTCOME_FAILURE and random.random() < 0.35:
            item = await _roll_expedition_item(session, int(player.id), player_level, depth.tier)
            if item:
                items_earned.append(item)

    # Legacy fields on active for display
    active.reward_gold = gold_gained
    active.reward_experience = exp_gained

    return {
        "gold_gained": gold_gained,
        "experience_gained": exp_gained,
        "waifu_exp_gained": waifu_exp_gained,
        "merc_exp_gained": merc_exp_gained,
        "enchant_stones": enchant_stones,
        "items_earned": items_earned,
        "leveled_up_ids": leveled_up_ids,
        "reward_type": rt,
    }


async def _roll_expedition_item(
    session: AsyncSession, player_id: int, player_level: int, depth_tier: int
) -> dict[str, Any] | None:
    try:
        from waifu_bot.services.item_service import ItemService

        act = max(1, min(5, 1 + (player_level - 1) // 15))
        rarity_roll = random.random()
        if depth_tier >= 5 and rarity_roll < 0.12:
            rarity = 4
        elif depth_tier >= 3 and rarity_roll < 0.25:
            rarity = 3
        else:
            rarity = 2 if random.random() < 0.4 else 1
        item_level = max(1, min(60, player_level + random.randint(-2, 3)))
        svc = ItemService()
        inv = await svc.generate_inventory_item(
            session=session,
            player_id=player_id,
            act=act,
            rarity=rarity,
            level=item_level,
            is_shop=False,
            plus_level=0,
        )
        await session.flush()
        name = getattr(inv, "_display_name", None) or (
            inv.item.name if getattr(inv, "item", None) else "Предмет"
        )
        return {
            "inventory_item_id": inv.id,
            "name": name,
            "rarity": int(inv.rarity or rarity),
            "level": int(inv.level or item_level),
        }
    except Exception:
        logger.exception("expedition item roll failed player_id=%s", player_id)
        return None
