"""Перековка: paid roll of legendary unique bonus. Rarity 5 only."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from waifu_bot.db import models as m
from waifu_bot.game.legendary_bonuses.drop_roll import _load_eligible_bonuses, pick_bonus_from_candidates
from waifu_bot.services.game_config_service import cfg_int, get_game_config_map
from waifu_bot.services.wallet import InsufficientCurrency, lock_player


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _flag(player: m.Player, key: str) -> bool:
    tp = player.tutorial_progress if isinstance(getattr(player, "tutorial_progress", None), dict) else {}
    return bool(tp.get(key))


def _set_flag(player: m.Player, key: str, value: bool = True) -> None:
    tp = dict(player.tutorial_progress) if isinstance(getattr(player, "tutorial_progress", None), dict) else {}
    tp[key] = value
    player.tutorial_progress = tp


def ember_cost(reroll_count: int) -> int:
    n = max(0, int(reroll_count or 0))
    return 1 + min(n, 8) // 3


def gold_cost(inv: m.InventoryItem, cfg: dict[str, str]) -> int:
    ilvl = int(getattr(inv, "total_level", None) or getattr(inv, "level", None) or 1)
    return int(cfg_int(cfg, "reforge.gold_per_ilvl", 400) * ilvl)


def _forbid(inv: m.InventoryItem) -> str | None:
    r = int(inv.rarity or 0)
    if r >= 6:
        return "raid_forbidden"
    if r != 5:
        return "not_legendary"
    return None


def _serialize_pending(p: m.ReforgePending) -> dict[str, Any]:
    remain = max(0, int((p.expires_at - _now()).total_seconds())) if p.expires_at else 0
    return {
        "id": int(p.id),
        "item_id": int(p.inventory_item_id),
        "options": list(p.options_json or []),
        "keep_bonus_ids": list(p.keep_bonus_ids or []),
        "expires_in_sec": remain,
        "ember_spent": int(p.ember_spent or 0),
        "gold_spent": int(p.gold_spent or 0),
    }


async def _load_item(session: AsyncSession, item_id: int, player_id: int) -> m.InventoryItem | None:
    return await session.scalar(
        select(m.InventoryItem)
        .options(selectinload(m.InventoryItem.item))
        .where(m.InventoryItem.id == int(item_id), m.InventoryItem.player_id == int(player_id))
        .with_for_update()
    )


async def _bonus_payloads(session: AsyncSession, ids: list[int]) -> list[dict[str, Any]]:
    if not ids:
        return []
    from waifu_bot.game.legendary_bonuses.loader import fetch_legendary_bonus_payloads

    class _Stub:
        def __init__(self, iid, bids):
            self.id = iid
            self.legendary_bonus_ids = bids
            self.is_legendary = True
            self.rarity = 5

    fake = _Stub(0, ids)
    try:
        mp = await fetch_legendary_bonus_payloads(session, [fake])  # type: ignore[list-item]
        return list(mp.get(0) or [])
    except Exception:
        return [{"id": int(i)} for i in ids]


async def quote(session: AsyncSession, player_id: int, item_id: int) -> dict[str, Any]:
    player = await session.get(m.Player, int(player_id))
    inv = await session.scalar(
        select(m.InventoryItem)
        .options(selectinload(m.InventoryItem.item))
        .where(m.InventoryItem.id == int(item_id), m.InventoryItem.player_id == int(player_id))
    )
    if not player or not inv:
        return {"error": "not_found"}
    err = _forbid(inv)
    if err:
        return {"error": err}
    cfg = await get_game_config_map(session)
    n = int(inv.reforge_reroll_count or 0)
    ember = ember_cost(n)
    gold = gold_cost(inv, cfg)
    open_pending = await session.scalar(
        select(m.ReforgePending).where(
            m.ReforgePending.inventory_item_id == int(inv.id),
            m.ReforgePending.status == "open",
        )
    )
    current_ids = list(inv.legendary_bonus_ids or [])
    current = await _bonus_payloads(session, current_ids)
    return {
        "item_id": int(inv.id),
        "current": current,
        "roll_index": n + 1,
        "cap": cfg_int(cfg, "reforge.cost_growth_cap", 8),
        "ember": ember,
        "gold": gold,
        "ack": _flag(player, "reforge_paid_ack"),
        "open_pending": _serialize_pending(open_pending) if open_pending else None,
    }


async def ack_paid(session: AsyncSession, player_id: int) -> dict[str, Any]:
    player = await lock_player(session, player_id)
    if not player:
        return {"error": "not_found"}
    _set_flag(player, "reforge_paid_ack", True)
    await session.commit()
    return {"ok": True}


async def _roll_options(session: AsyncSession, inv: m.InventoryItem, cfg: dict[str, str]) -> list[dict]:
    current = {int(x) for x in (inv.legendary_bonus_ids or [])}
    candidates = await _load_eligible_bonuses(
        session, tier=int(inv.tier or 1), slot_type=str(inv.slot_type or "")
    )
    pool = [c for c in candidates if int(c.get("id") or 0) not in current]
    if not pool:
        pool = list(candidates)
    n = cfg_int(cfg, "reforge.option_count", 3)
    out: list[dict] = []
    used: set[int] = set()
    for _ in range(max(1, n)):
        remain = [c for c in pool if int(c.get("id") or 0) not in used]
        if not remain:
            break
        picked = pick_bonus_from_candidates(
            remain, tier=int(inv.tier or 1), slot_type=str(inv.slot_type or "")
        )
        if picked is None:
            break
        bid = int(picked["id"])
        used.add(bid)
        out.append(
            {
                "id": bid,
                "bonus_key": picked.get("bonus_key"),
                "params": picked.get("params") or {},
            }
        )
    return out


async def start_roll(session: AsyncSession, player_id: int, item_id: int) -> dict[str, Any]:
    player = await lock_player(session, player_id)
    if not player:
        return {"error": "not_found"}
    inv = await _load_item(session, item_id, player_id)
    if not inv:
        return {"error": "not_found"}
    err = _forbid(inv)
    if err:
        return {"error": err}
    open_pending = await session.scalar(
        select(m.ReforgePending).where(
            m.ReforgePending.inventory_item_id == int(inv.id),
            m.ReforgePending.status == "open",
        )
    )
    if open_pending is not None:
        if open_pending.expires_at and open_pending.expires_at <= _now():
            open_pending.status = "expired"
        else:
            return {"error": "open_pending", "pending": _serialize_pending(open_pending)}
    cfg = await get_game_config_map(session)
    ember = ember_cost(int(inv.reforge_reroll_count or 0))
    gold = gold_cost(inv, cfg)
    ttl = cfg_int(cfg, "reforge.pending_ttl_sec", 600)
    txn = m.ReforgeTransaction(
        player_id=int(player_id),
        inventory_item_id=int(inv.id),
        ember_spent=int(ember),
        gold_spent=int(gold),
    )
    session.add(txn)
    await session.flush()
    from waifu_bot.services import wallet as wallet_svc

    try:
        await wallet_svc.spend(
            session,
            int(player_id),
            "legendary_ember",
            int(ember),
            source="reforge",
            ref_type="reforge_txn_ember",
            ref_id=int(txn.id),
        )
        await wallet_svc.spend_gold(
            session,
            player,
            int(gold),
            source="reforge",
            ref_type="reforge_txn",
            ref_id=int(txn.id),
        )
    except InsufficientCurrency as exc:
        return {"error": "insufficient", "currency": exc.currency_key, "have": exc.have, "need": exc.need}
    options = await _roll_options(session, inv, cfg)
    pending = m.ReforgePending(
        player_id=int(player_id),
        inventory_item_id=int(inv.id),
        status="open",
        options_json=options,
        keep_bonus_ids=list(inv.legendary_bonus_ids or []),
        ember_spent=int(ember),
        gold_spent=int(gold),
        expires_at=_now() + timedelta(seconds=ttl),
        transaction_id=int(txn.id),
    )
    session.add(pending)
    try:
        async with session.begin_nested():
            await session.flush()
    except IntegrityError:
        existing = await session.scalar(
            select(m.ReforgePending).where(
                m.ReforgePending.inventory_item_id == int(inv.id),
                m.ReforgePending.status == "open",
            )
        )
        if existing:
            return {"error": "open_pending", "pending": _serialize_pending(existing)}
        return {"error": "open_pending"}
    inv.reforge_reroll_count = int(inv.reforge_reroll_count or 0) + 1
    await session.commit()
    return {"pending": _serialize_pending(pending)}


async def apply_choice(
    session: AsyncSession,
    player_id: int,
    item_id: int,
    *,
    option_index: int | None,
    keep: bool = False,
) -> dict[str, Any]:
    player = await lock_player(session, player_id)
    if not player:
        return {"error": "not_found"}
    pending = await session.scalar(
        select(m.ReforgePending)
        .where(
            m.ReforgePending.inventory_item_id == int(item_id),
            m.ReforgePending.player_id == int(player_id),
            m.ReforgePending.status == "open",
        )
        .with_for_update()
    )
    if pending is None:
        return {"error": "no_pending"}
    if pending.expires_at and pending.expires_at <= _now():
        pending.status = "expired"
        await session.commit()
        return {"error": "expired"}
    inv = await _load_item(session, item_id, player_id)
    if not inv:
        return {"error": "not_found"}
    if keep:
        pending.status = "kept"
        await session.commit()
        return {"ok": True, "kept": True, "bonus_ids": list(inv.legendary_bonus_ids or [])}
    opts = list(pending.options_json or [])
    idx = int(option_index if option_index is not None else -1)
    if idx < 0 or idx >= len(opts):
        return {"error": "invalid_option"}
    chosen = opts[idx]
    bid = int(chosen.get("id") or 0)
    if bid <= 0:
        return {"error": "invalid_option"}
    from sqlalchemy.orm.attributes import flag_modified

    from waifu_bot.services.legendary_combat import LegendaryCombatBridge

    inv.legendary_bonus_ids = [bid]
    flag_modified(inv, "legendary_bonus_ids")
    pending.status = "applied"
    await session.flush()
    # Reload this player's equipped bonuses for the next fight. Do not touch _CANDIDATE_CACHE.
    bridge = LegendaryCombatBridge()
    await bridge.load(session, int(player_id))
    await session.commit()
    return {"ok": True, "bonus_ids": [bid]}


async def burn_pending(session: AsyncSession, player_id: int, item_id: int) -> dict[str, Any]:
    player = await lock_player(session, player_id)
    if not player:
        return {"error": "not_found"}
    pending = await session.scalar(
        select(m.ReforgePending)
        .where(
            m.ReforgePending.inventory_item_id == int(item_id),
            m.ReforgePending.player_id == int(player_id),
            m.ReforgePending.status == "open",
        )
        .with_for_update()
    )
    if pending is None:
        return {"error": "no_pending"}
    pending.status = "burned"
    await session.commit()
    return {"ok": True, "burned": True}
