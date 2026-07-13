"""Tutorial / onboarding progress helpers."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db import models as m
from waifu_bot.db.models import Player
from waifu_bot.db.models.item import ItemType

logger = logging.getLogger(__name__)

TUTORIAL_VERSION = 1

# Flow ids shown in the client (must match TUTORIAL_FLOWS keys in tutorial.js)
KNOWN_TUTORIAL_STEPS: tuple[str, ...] = (
    "waifu_gen",
    "waifu_gen_step2",
    "intro",
    "equip",
    "paperdoll",
    "shop",
    "tavern",
    "dungeons",
    "expeditions",
    "caravan",
    "guild",
    "training",
)

INTRO_TUTORIAL_GOLD_REWARD = 500
SHOP_KIT_ID = "shop_loop"
PAPERDOLL_KIT_ID = "paperdoll"
SHOP_KIT_MIN_DUST = 50
SHOP_KIT_GOLD_BUFFER = 80
SHOP_KIT_JUNK_NAME = "Учебный хлам"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_tutorial_progress(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    completed_raw = raw.get("completed")
    completed: dict[str, str] = {}
    if isinstance(completed_raw, dict):
        for k, v in completed_raw.items():
            if isinstance(k, str) and isinstance(v, str):
                completed[k] = v
    sell_raw = raw.get("shop_kit_sell_item_id")
    sell_id: int | None = None
    if isinstance(sell_raw, int):
        sell_id = sell_raw
    elif isinstance(sell_raw, str) and sell_raw.isdigit():
        sell_id = int(sell_raw)
    buy_slot_raw = raw.get("shop_kit_buy_slot")
    buy_slot: int | None = None
    if isinstance(buy_slot_raw, int):
        buy_slot = buy_slot_raw
    elif isinstance(buy_slot_raw, str) and buy_slot_raw.isdigit():
        buy_slot = int(buy_slot_raw)
    return {
        "version": int(raw.get("version") or TUTORIAL_VERSION),
        "completed": completed,
        "skipped": bool(raw.get("skipped")),
        "intro_reward_claimed": bool(raw.get("intro_reward_claimed")),
        "shop_kit_claimed": bool(raw.get("shop_kit_claimed")),
        "shop_kit_sell_item_id": sell_id,
        "shop_kit_buy_slot": buy_slot,
        "paperdoll_kit_claimed": bool(raw.get("paperdoll_kit_claimed")),
    }


def tutorial_state_from_player(player: Player) -> dict[str, Any]:
    return normalize_tutorial_progress(getattr(player, "tutorial_progress", None))


async def get_or_create_player(session: AsyncSession, player_id: int) -> Player:
    result = await session.execute(select(Player).where(Player.id == player_id))
    player = result.scalar_one_or_none()
    if player is None:
        player = Player(id=player_id)
        session.add(player)
        await session.flush()
    return player


async def get_tutorial_state(session: AsyncSession, player_id: int) -> dict[str, Any]:
    player = await get_or_create_player(session, player_id)
    return tutorial_state_from_player(player)


async def complete_tutorial_step(
    session: AsyncSession,
    player_id: int,
    step_id: str,
) -> tuple[dict[str, Any], int | None]:
    """Mark a tutorial flow as completed. Returns (state, gold_reward_or_none)."""
    if step_id not in KNOWN_TUTORIAL_STEPS:
        raise ValueError(f"unknown_tutorial_step:{step_id}")

    player = await get_or_create_player(session, player_id)
    state = normalize_tutorial_progress(player.tutorial_progress)
    now = _utc_now_iso()
    state["completed"][step_id] = now
    state["version"] = TUTORIAL_VERSION

    gold_reward: int | None = None
    if step_id == "intro" and not state.get("intro_reward_claimed"):
        gold_reward = INTRO_TUTORIAL_GOLD_REWARD
        player.gold = int(player.gold or 0) + gold_reward
        state["intro_reward_claimed"] = True

    player.tutorial_progress = state
    await session.flush()
    return state, gold_reward


async def skip_all_tutorials(session: AsyncSession, player_id: int) -> dict[str, Any]:
    player = await get_or_create_player(session, player_id)
    state = normalize_tutorial_progress(player.tutorial_progress)
    now = _utc_now_iso()
    for step_id in KNOWN_TUTORIAL_STEPS:
        state["completed"].setdefault(step_id, now)
    state["skipped"] = True
    state["version"] = TUTORIAL_VERSION
    player.tutorial_progress = state
    await session.flush()
    return state


async def reset_tutorial_progress(session: AsyncSession, player_id: int) -> dict[str, Any]:
    player = await get_or_create_player(session, player_id)
    old = normalize_tutorial_progress(player.tutorial_progress)
    state = normalize_tutorial_progress({})
    # Replay from settings must not re-grant intro gold / shop kit.
    if old.get("intro_reward_claimed"):
        state["intro_reward_claimed"] = True
    if old.get("shop_kit_claimed"):
        state["shop_kit_claimed"] = True
        state["shop_kit_sell_item_id"] = old.get("shop_kit_sell_item_id")
        state["shop_kit_buy_slot"] = old.get("shop_kit_buy_slot")
    if old.get("paperdoll_kit_claimed"):
        state["paperdoll_kit_claimed"] = True
    player.tutorial_progress = state
    await session.flush()
    return state


async def _find_cheapest_shop_offer(
    session: AsyncSession, player_id: int, act: int
) -> tuple[int | None, int]:
    """Return (slot, price) for cheapest unsold offer, or (None, 0)."""
    try:
        from waifu_bot.services.shop import ShopService

        svc = ShopService()
        data = await svc.get_shop_inventory(session, player_id, act=act)
        items = list(data.get("items") or []) if isinstance(data, dict) else []
    except Exception:
        logger.exception("tutorial shop inventory lookup failed player=%s", player_id)
        return None, 0

    best_slot: int | None = None
    best_price = 0
    for idx, offer in enumerate(items):
        if not isinstance(offer, dict) or offer.get("sold"):
            continue
        price = offer.get("price")
        if price is None:
            continue
        try:
            price_i = int(price)
        except (TypeError, ValueError):
            continue
        if price_i <= 0:
            continue
        slot_raw = offer.get("slot") or offer.get("offer_slot") or offer.get("shop_slot") or (idx + 1)
        try:
            slot_i = int(slot_raw)
        except (TypeError, ValueError):
            continue
        if best_slot is None or price_i < best_price:
            best_slot = slot_i
            best_price = price_i
    return best_slot, best_price


async def _create_junk_inventory_item(session: AsyncSession, player_id: int) -> m.InventoryItem:
    item = m.Item(
        name=SHOP_KIT_JUNK_NAME,
        description="Учебный предмет для продажи в обучении магазина.",
        rarity=1,
        tier=1,
        level=1,
        item_type=int(ItemType.RING_1),
        damage=None,
        attack_speed=None,
        weapon_type=None,
        attack_type=None,
        required_level=1,
        required_strength=None,
        required_agility=None,
        required_intelligence=None,
        affixes=None,
        base_value=15,
        is_legendary=False,
    )
    session.add(item)
    await session.flush()

    inv = m.InventoryItem(
        player_id=player_id,
        item_id=item.id,
        rarity=1,
        tier=1,
        level=1,
        base_level=1,
        total_level=1,
        plus_level_source=0,
        is_legendary=False,
        slot_type="ring",
        requirements={"level": 1},
        enchant_level=0,
        enchant_dmg_step=0,
        enchant_arm_step=0,
        enchant_sec_step=0.0,
        is_broken=False,
    )
    session.add(inv)
    await session.flush()
    return inv


async def provision_tutorial_kit(
    session: AsyncSession,
    player_id: int,
    kit_id: str,
) -> dict[str, Any]:
    """Grant resources for an interactive tutorial kit (idempotent)."""
    if kit_id == PAPERDOLL_KIT_ID:
        return await _provision_paperdoll_kit(session, player_id)
    if kit_id != SHOP_KIT_ID:
        raise ValueError(f"unknown_tutorial_kit:{kit_id}")

    player = await get_or_create_player(session, player_id)
    state = normalize_tutorial_progress(player.tutorial_progress)

    if state.get("shop_kit_claimed"):
        return {
            "tutorial": state,
            "gold_granted": 0,
            "dust_granted": 0,
            "sell_item_id": state.get("shop_kit_sell_item_id"),
            "buy_hint": {
                "slot": state.get("shop_kit_buy_slot"),
                "price": None,
            },
            "already_claimed": True,
        }

    act = max(1, int(getattr(player, "current_act", None) or 1))
    buy_slot, buy_price = await _find_cheapest_shop_offer(session, player_id, act)

    need_gold = max(buy_price + SHOP_KIT_GOLD_BUFFER, SHOP_KIT_GOLD_BUFFER)
    have_gold = int(player.gold or 0)
    gold_granted = max(0, need_gold - have_gold)
    if gold_granted:
        player.gold = have_gold + gold_granted

    have_dust = int(getattr(player, "enchant_dust", 0) or 0)
    dust_granted = max(0, SHOP_KIT_MIN_DUST - have_dust)
    if dust_granted:
        player.enchant_dust = have_dust + dust_granted

    junk = await _create_junk_inventory_item(session, player_id)

    state["shop_kit_claimed"] = True
    state["shop_kit_sell_item_id"] = int(junk.id)
    state["shop_kit_buy_slot"] = buy_slot
    state["version"] = TUTORIAL_VERSION
    player.tutorial_progress = state
    await session.flush()

    return {
        "tutorial": state,
        "gold_granted": gold_granted,
        "dust_granted": dust_granted,
        "sell_item_id": int(junk.id),
        "buy_hint": {"slot": buy_slot, "price": buy_price or None},
        "already_claimed": False,
    }


async def _provision_paperdoll_kit(
    session: AsyncSession,
    player_id: int,
) -> dict[str, Any]:
    """Grant one bonus paperdoll generation only if first free slot is already used."""
    from waifu_bot.services.paperdoll_quota import paperdoll_generations_remaining

    player = await get_or_create_player(session, player_id)
    state = normalize_tutorial_progress(player.tutorial_progress)

    if state.get("paperdoll_kit_claimed"):
        return {
            "tutorial": state,
            "bonus_granted": 0,
            "already_claimed": True,
        }

    result = await session.execute(
        select(m.MainWaifu).where(m.MainWaifu.player_id == player_id)
    )
    main = result.scalar_one_or_none()
    bonus_granted = 0
    if main is not None:
        has_image = bool((getattr(main, "paperdoll_image_data", None) or "").strip())
        remaining = paperdoll_generations_remaining(main)
        if has_image and remaining == 0:
            main.paperdoll_bonus_generations = int(main.paperdoll_bonus_generations or 0) + 1
            bonus_granted = 1

    state["paperdoll_kit_claimed"] = True
    state["version"] = TUTORIAL_VERSION
    player.tutorial_progress = state
    await session.flush()

    return {
        "tutorial": state,
        "bonus_granted": bonus_granted,
        "already_claimed": False,
    }
