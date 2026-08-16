"""Sticky t_bonus → m_/s_ overlays for linked multi-client accounts."""
from __future__ import annotations

import hashlib
import logging
import random
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from waifu_bot.db import models as m
from waifu_bot.game.bonus_channels import (
    CHANNEL_COMMON,
    CHANNEL_MOBILE,
    CHANNEL_STEAM,
    CHANNEL_TELEGRAM,
    client_channel,
    infer_channel_from_stat,
    normalize_channel,
)

logger = logging.getLogger(__name__)

# Seed catalog rows used when remapping telegram-only affixes
_MOBILE_POOL_SEED = [
    ("Шаги: сила", "step_power", 1, 3, 1),
    ("Шаги: выносливость", "step_endurance", 2, 5, 1),
    ("Активность: темп", "step_tempo", 1, 2, 2),
    ("Пеший удар", "step_strike", 3, 8, 2),
    ("Маршрут охотника", "step_hunt", 2, 6, 3),
]
_STEAM_POOL_SEED = [
    ("Клики: сила", "click_power", 1, 3, 1),
    ("Клики: темп", "click_tempo", 1, 2, 2),
    ("ПК: фокус", "click_focus", 2, 5, 2),
    ("Серия кликов", "click_streak", 3, 8, 3),
]


def _seeded_rng(item_id: int, channel: str, slot: int) -> random.Random:
    h = hashlib.sha256(f"{item_id}:{channel}:{slot}".encode("utf-8")).hexdigest()
    return random.Random(int(h[:16], 16))


def _affix_channel(row: m.Affix | None, inv_affix: m.InventoryAffix) -> str:
    if row is not None and getattr(row, "channel", None):
        return normalize_channel(row.channel)
    return infer_channel_from_stat(getattr(inv_affix, "stat", None))


async def ensure_channel_catalog(session: AsyncSession) -> None:
    """Ensure minimal m_/s_ affix pools exist for remap."""
    for channel, seed in (
        (CHANNEL_MOBILE, _MOBILE_POOL_SEED),
        (CHANNEL_STEAM, _STEAM_POOL_SEED),
    ):
        q = await session.execute(
            select(m.Affix.id).where(m.Affix.channel == channel).limit(1)
        )
        if q.scalar_one_or_none() is not None:
            continue
        for name, stat, vmin, vmax, tier in seed:
            session.add(
                m.Affix(
                    name=name,
                    kind="affix",
                    stat=stat,
                    value_min=vmin,
                    value_max=vmax,
                    is_percent=False,
                    tier=tier,
                    min_level=1,
                    channel=channel,
                    applies_to=["weapon_1h", "weapon_2h", "armor", "ring", "amulet"],
                    weight=10,
                )
            )
        await session.flush()
        logger.info("Seeded %s channel affix pool", channel)


async def _pool_for_channel(session: AsyncSession, channel: str, tier: int) -> list[m.Affix]:
    q = await session.execute(
        select(m.Affix).where(m.Affix.channel == channel).order_by(m.Affix.tier, m.Affix.id)
    )
    rows = list(q.scalars().all())
    same = [r for r in rows if int(r.tier or 1) == int(tier or 1)]
    return same or rows


async def ensure_channel_overlays(
    session: AsyncSession,
    player_id: int,
    client: str,
) -> dict[str, Any]:
    """
    Idempotent: for mobile/steam, create sticky overlays replacing telegram-channel
    affixes. Returns summary for API.
    """
    target = client_channel(client)
    if target not in (CHANNEL_MOBILE, CHANNEL_STEAM):
        return {"changed": 0, "channel": target}

    await ensure_channel_catalog(session)

    q = await session.execute(
        select(m.InventoryItem)
        .options(selectinload(m.InventoryItem.affixes))
        .where(m.InventoryItem.player_id == player_id)
    )
    items = list(q.scalars().all())

    # Load catalog affixes by matching name+stat loosely via Affix table
    cat_q = await session.execute(select(m.Affix))
    catalog = list(cat_q.scalars().all())
    by_stat: dict[str, m.Affix] = {}
    for a in catalog:
        by_stat.setdefault(str(a.stat), a)

    changed = 0
    for inv in items:
        overrides = dict(inv.channel_bonus_overrides or {})
        if target in overrides and overrides[target]:
            continue  # already sticky

        overlay: list[dict[str, Any]] = []
        slot = 0
        for ia in inv.affixes or []:
            cat = by_stat.get(str(ia.stat))
            ch = _affix_channel(cat, ia)
            if ch != CHANNEL_TELEGRAM:
                continue
            tier = int(
                getattr(ia, "affix_tier", None)
                or getattr(ia, "tier", None)
                or (cat.tier if cat else 1)
                or 1
            )
            pool = await _pool_for_channel(session, target, tier)
            if not pool:
                continue
            rng = _seeded_rng(int(inv.id), target, slot)
            pick = rng.choice(pool)
            lo = int(pick.value_min)
            hi = int(pick.value_max)
            if hi < lo:
                lo, hi = hi, lo
            value = rng.randint(lo, hi) if hi > lo else lo
            overlay.append(
                {
                    "source_stat": ia.stat,
                    "source_name": ia.name,
                    "name": pick.name,
                    "stat": pick.stat,
                    "value": value,
                    "is_percent": bool(pick.is_percent),
                    "tier": int(pick.tier),
                    "channel": target,
                    "kind": pick.kind,
                }
            )
            slot += 1

        if overlay:
            overrides[target] = overlay
            inv.channel_bonus_overrides = overrides
            changed += 1

    if changed:
        await session.flush()

    msg = None
    if changed:
        label = "шаги" if target == CHANNEL_MOBILE else "клики"
        msg = f"Бонусы чата адаптированы под {label} на {changed} предмет(ах) (зафиксировано)."
    return {"changed": changed, "channel": target, "message": msg}


def resolve_item_bonuses_for_client(inv: m.InventoryItem, client: str) -> list[dict[str, Any]]:
    """Build display/combat bonus list: common + client channel (with sticky overlay)."""
    cc = client_channel(client)
    overrides = (inv.channel_bonus_overrides or {}).get(cc) or []
    if overrides:
        # Prefer sticky overlay for replaced telegram slots; still include native common/m
        out = [dict(x, channel=x.get("channel") or cc) for x in overrides]
        for ia in inv.affixes or []:
            ch = infer_channel_from_stat(ia.stat)
            if ch == CHANNEL_COMMON or ch == cc:
                out.append(
                    {
                        "name": ia.name,
                        "stat": ia.stat,
                        "value": ia.value,
                        "is_percent": bool(getattr(ia, "is_percent", False)),
                        "channel": ch,
                        "kind": getattr(ia, "kind", "affix"),
                    }
                )
        return out

    out = []
    for ia in inv.affixes or []:
        ch = infer_channel_from_stat(ia.stat)
        if ch == CHANNEL_COMMON or ch == cc:
            out.append(
                {
                    "name": ia.name,
                    "stat": ia.stat,
                    "value": ia.value,
                    "is_percent": bool(getattr(ia, "is_percent", False)),
                    "channel": ch,
                    "kind": getattr(ia, "kind", "affix"),
                }
            )
        # telegram affixes ignored on mobile/steam until overlay exists
    return out
