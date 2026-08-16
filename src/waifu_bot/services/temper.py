"""Закалка: paid roll of prefix/suffix on Rare/Epic items."""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from waifu_bot.db import models as m
from waifu_bot.services.dismantle import calculate_dismantle_dust
from waifu_bot.services.game_config_service import cfg_float, cfg_int, get_game_config_map
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


def temper_costs(inv: m.InventoryItem, cfg: dict[str, str]) -> tuple[int, int]:
    rarity = int(inv.rarity or 1)
    tier = int(inv.tier or 1)
    n = int(getattr(inv, "temper_reroll_count", 0) or 0)
    cap = cfg_int(cfg, "temper.cost_growth_cap", 8)
    dust_base = calculate_dismantle_dust(rarity=rarity, tier=tier, cfg=cfg)
    salvage = cfg_float(cfg, f"temper.salvage_mult_{rarity}", 4.0 if rarity == 3 else 3.5)
    dust = int(math.floor(dust_base * salvage * (1.0 + min(n, cap) * 0.15)))
    act = 1
    req = inv.requirements if isinstance(inv.requirements, dict) else {}
    try:
        act = max(1, min(5, int((int(req.get("level") or inv.level or 1) - 1) // 12) + 1))
    except Exception:
        act = 1
    gold_base = cfg_int(cfg, "temper.gold_base", 80)
    act_mult = cfg_float(cfg, f"temper.act_mult_{act}", 1.0)
    ilvl = int(getattr(inv, "total_level", None) or getattr(inv, "level", None) or 1)
    gold = int(math.floor(gold_base * ilvl * act_mult))
    return max(1, dust), max(1, gold)


def _affix_snapshot(row: m.InventoryAffix) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "name": str(row.name or ""),
        "stat": str(row.stat or ""),
        "value": str(row.value or ""),
        "is_percent": bool(row.is_percent),
        "kind": str(row.kind or ""),
        "tier": int(row.tier or 1),
        "family_id": int(row.family_id) if row.family_id is not None else None,
        "affix_tier": int(row.affix_tier) if row.affix_tier is not None else None,
        "exclusive_group": row.exclusive_group,
        "level_delta": int(row.level_delta or 0),
    }


async def _load_item(session: AsyncSession, item_id: int, player_id: int) -> m.InventoryItem | None:
    return await session.scalar(
        select(m.InventoryItem)
        .options(selectinload(m.InventoryItem.affixes), selectinload(m.InventoryItem.item))
        .where(m.InventoryItem.id == int(item_id), m.InventoryItem.player_id == int(player_id))
        .with_for_update()
    )


def _raid_or_legendary(inv: m.InventoryItem) -> str | None:
    r = int(inv.rarity or 0)
    if r >= 6:
        return "raid_forbidden"
    if r >= 5:
        return "legendary_no_temper"
    if r not in (3, 4):
        return "rarity_not_temperable"
    return None


async def _roll_options(session: AsyncSession, inv: m.InventoryItem, affix: m.InventoryAffix, cfg: dict[str, str]) -> list[dict]:
    from waifu_bot.services.item_service import ItemService, _affix_tier_cap_for_generation

    svc = ItemService()
    ilvl = int(getattr(inv, "total_level", None) or getattr(inv, "level", None) or 1)
    act = max(1, min(5, int((ilvl - 1) // 12) + 1))
    cap = _affix_tier_cap_for_generation(act, ilvl)
    base = SimpleNamespace(slot_type=inv.slot_type, attack_type=inv.attack_type)
    pairs = await svc._get_diablo_candidates(
        session, base, cap, ilvl, item_rarity=int(inv.rarity or 3)
    )
    exclude_fid = int(affix.family_id) if affix.family_id is not None else None
    occupied_eg = {
        str(a.exclusive_group)
        for a in (inv.affixes or [])
        if a.id != affix.id and a.exclusive_group
    }
    want_kind = "prefix" if str(affix.kind or "") == "affix" else "suffix"
    filtered: list[tuple[m.AffixFamily, m.AffixFamilyTier]] = []
    for fam, tr in pairs:
        k = (getattr(fam, "kind", "") or "").lower()
        if k != want_kind:
            continue
        if exclude_fid is not None and int(fam.id) == exclude_fid:
            continue
        eg = str(getattr(fam, "exclusive_group", "") or "")
        if eg and eg in occupied_eg:
            continue
        filtered.append((fam, tr))
    if not filtered:
        filtered = [(fam, tr) for fam, tr in pairs if (getattr(fam, "kind", "") or "").lower() == want_kind]
    n = cfg_int(cfg, "temper.option_count", 3)
    rng = random.Random()
    rng.shuffle(filtered)
    picked = filtered[: max(1, n)]
    out = []
    for fam, tr in picked:
        vmin = float(tr.value_min or 1)
        vmax = float(tr.value_max or vmin)
        if vmax < vmin:
            vmax = vmin
        value = int(rng.randint(int(vmin), int(max(vmin, vmax))))
        affix_tier = int(tr.affix_tier or 1)
        family_id = int(fam.id)
        effect_key = str(getattr(fam, "effect_key", None) or getattr(fam, "family_id", "") or "stat")
        fam_kind = (getattr(fam, "kind", "") or "").lower()
        inv_kind = "affix" if fam_kind == "prefix" else "suffix"
        if inv_kind == "affix":
            name_ru = svc._resolve_prefix_name_ru(
                effect_key, affix_tier, family_id=str(getattr(fam, "family_id", "") or "") or None
            )
        else:
            name_ru = svc._resolve_suffix_name_ru(str(getattr(fam, "family_id", "") or ""), affix_tier)
        out.append(
            {
                "name": name_ru,
                "stat": effect_key,
                "value": str(int(value)),
                "is_percent": bool(svc._is_percent_effect_key(effect_key)),
                "kind": inv_kind,
                "tier": affix_tier,
                "family_id": family_id,
                "affix_tier": affix_tier,
                "exclusive_group": getattr(fam, "exclusive_group", None),
                "level_delta": int(tr.level_delta_min or 0),
            }
        )
    return out


async def quote(session: AsyncSession, player_id: int, item_id: int, affix_row_id: int) -> dict[str, Any]:
    player = await session.get(m.Player, int(player_id))
    inv = await _load_item(session, item_id, player_id)
    if not player or not inv:
        return {"error": "not_found"}
    err = _raid_or_legendary(inv)
    if err:
        return {"error": err}
    affix = next((a for a in (inv.affixes or []) if int(a.id) == int(affix_row_id)), None)
    if affix is None:
        return {"error": "affix_not_found"}
    cfg = await get_game_config_map(session)
    dust, gold = temper_costs(inv, cfg)
    n = int(inv.temper_reroll_count or 0)
    open_pending = await session.scalar(
        select(m.TemperPending).where(
            m.TemperPending.inventory_item_id == int(inv.id),
            m.TemperPending.status == "open",
        )
    )
    return {
        "item_id": int(inv.id),
        "affix_row_id": int(affix.id),
        "current": {"name": affix.name, "value": affix.value},
        "roll_index": n + 1,
        "cap": cfg_int(cfg, "temper.cost_growth_cap", 8),
        "dust": dust,
        "gold": gold,
        "ack": _flag(player, "temper_paid_ack"),
        "open_pending": _serialize_pending(open_pending) if open_pending else None,
    }


def _serialize_pending(p: m.TemperPending) -> dict[str, Any]:
    remain = max(0, int((p.expires_at - _now()).total_seconds())) if p.expires_at else 0
    return {
        "id": int(p.id),
        "item_id": int(p.inventory_item_id),
        "affix_row_id": int(p.affix_row_id),
        "options": list(p.options_json or []),
        "keep": dict(p.keep_snapshot or {}),
        "expires_in_sec": remain,
        "dust_spent": int(p.dust_spent or 0),
        "gold_spent": int(p.gold_spent or 0),
    }


async def ack_paid(session: AsyncSession, player_id: int) -> dict[str, Any]:
    player = await lock_player(session, player_id)
    if not player:
        return {"error": "not_found"}
    _set_flag(player, "temper_paid_ack", True)
    await session.commit()
    return {"ok": True}


async def start_roll(
    session: AsyncSession, player_id: int, item_id: int, affix_row_id: int
) -> dict[str, Any]:
    player = await lock_player(session, player_id)
    if not player:
        return {"error": "not_found"}
    inv = await _load_item(session, item_id, player_id)
    if not inv:
        return {"error": "not_found"}
    err = _raid_or_legendary(inv)
    if err:
        return {"error": err}
    affix = next((a for a in (inv.affixes or []) if int(a.id) == int(affix_row_id)), None)
    if affix is None:
        return {"error": "affix_not_found"}
    open_pending = await session.scalar(
        select(m.TemperPending).where(
            m.TemperPending.inventory_item_id == int(inv.id),
            m.TemperPending.status == "open",
        )
    )
    if open_pending is not None:
        if open_pending.expires_at and open_pending.expires_at <= _now():
            open_pending.status = "expired"
        else:
            return {"error": "open_pending", "pending": _serialize_pending(open_pending)}
    cfg = await get_game_config_map(session)
    dust, gold = temper_costs(inv, cfg)
    ttl = cfg_int(cfg, "temper.pending_ttl_sec", 600)
    from waifu_bot.services import wallet as wallet_svc

    txn = m.TemperTransaction(
        player_id=int(player_id),
        inventory_item_id=int(inv.id),
        dust_spent=int(dust),
        gold_spent=int(gold),
    )
    session.add(txn)
    await session.flush()
    try:
        await wallet_svc.spend(
            session,
            int(player_id),
            "enchant_dust",
            int(dust),
            source="temper",
            ref_type="temper_txn_dust",
            ref_id=int(txn.id),
        )
        await wallet_svc.spend_gold(
            session,
            player,
            int(gold),
            source="temper",
            ref_type="temper_txn",
            ref_id=int(txn.id),
        )
    except InsufficientCurrency as exc:
        return {"error": "insufficient", "currency": exc.currency_key, "have": exc.have, "need": exc.need}
    options = await _roll_options(session, inv, affix, cfg)
    pending = m.TemperPending(
        player_id=int(player_id),
        inventory_item_id=int(inv.id),
        affix_row_id=int(affix.id),
        status="open",
        options_json=options,
        keep_snapshot=_affix_snapshot(affix),
        dust_spent=int(dust),
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
            select(m.TemperPending).where(
                m.TemperPending.inventory_item_id == int(inv.id),
                m.TemperPending.status == "open",
            )
        )
        if existing:
            return {"error": "open_pending", "pending": _serialize_pending(existing)}
        return {"error": "open_pending"}
    inv.temper_reroll_count = int(inv.temper_reroll_count or 0) + 1
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
        select(m.TemperPending)
        .where(
            m.TemperPending.inventory_item_id == int(item_id),
            m.TemperPending.player_id == int(player_id),
            m.TemperPending.status == "open",
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
    affix = next((a for a in (inv.affixes or []) if int(a.id) == int(pending.affix_row_id)), None)
    if affix is None:
        pending.status = "expired"
        await session.commit()
        return {"error": "affix_not_found"}
    if keep:
        pending.status = "kept"
        await session.commit()
        return {"ok": True, "kept": True, "current": _affix_snapshot(affix)}
    opts = list(pending.options_json or [])
    idx = int(option_index if option_index is not None else -1)
    if idx < 0 or idx >= len(opts):
        return {"error": "invalid_option"}
    chosen = dict(opts[idx])
    affix.name = str(chosen.get("name") or affix.name)
    affix.stat = str(chosen.get("stat") or affix.stat)
    affix.value = str(chosen.get("value") or affix.value)
    affix.is_percent = bool(chosen.get("is_percent"))
    affix.kind = str(chosen.get("kind") or affix.kind)
    affix.tier = int(chosen.get("tier") or affix.tier or 1)
    affix.family_id = chosen.get("family_id")
    affix.affix_tier = chosen.get("affix_tier")
    affix.exclusive_group = chosen.get("exclusive_group")
    affix.level_delta = int(chosen.get("level_delta") or 0)
    pending.status = "applied"
    await session.commit()
    return {"ok": True, "applied": _affix_snapshot(affix)}


async def burn_pending(session: AsyncSession, player_id: int, item_id: int) -> dict[str, Any]:
    player = await lock_player(session, player_id)
    if not player:
        return {"error": "not_found"}
    pending = await session.scalar(
        select(m.TemperPending)
        .where(
            m.TemperPending.inventory_item_id == int(item_id),
            m.TemperPending.player_id == int(player_id),
            m.TemperPending.status == "open",
        )
        .with_for_update()
    )
    if pending is None:
        return {"error": "no_pending"}
    pending.status = "burned"
    await session.commit()
    return {"ok": True, "burned": True}
