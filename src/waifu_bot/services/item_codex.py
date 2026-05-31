"""Item and affix library (codex) discovery tracking."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db import models as m
from waifu_bot.db.models.item import PlayerAffixCodex, PlayerItemCodex

logger = logging.getLogger(__name__)

CATALOG_LEGACY = "legacy_affix"
CATALOG_DIABLO = "diablo_family"


async def resolve_base_template_id(
    session: AsyncSession, inv: m.InventoryItem
) -> int | None:
    """Map an inventory row to item_base_templates.id via base item name + tier."""
    tier = int(getattr(inv, "tier", None) or 0)
    if tier < 1:
        item = getattr(inv, "item", None)
        if item is not None:
            tier = int(getattr(item, "tier", None) or 0)
    if tier < 1:
        return None

    base_name = ""
    item = getattr(inv, "item", None)
    if item is not None:
        base_name = str(getattr(item, "name", "") or "").strip()
    if not base_name:
        base_name = str(getattr(inv, "_display_name", "") or "").strip()
    if not base_name or base_name.lower() in ("предмет", "item"):
        return None

    try:
        row = await session.execute(
            text(
                "SELECT id FROM item_base_templates "
                "WHERE name = :name AND tier = :tier LIMIT 1"
            ),
            {"name": base_name, "tier": int(tier)},
        )
        tid = row.scalar()
        return int(tid) if tid is not None else None
    except Exception:
        logger.debug("resolve_base_template_id failed for name=%s tier=%s", base_name, tier)
        return None


async def mark_item_seen(
    session: AsyncSession, player_id: int, base_template_id: int | None
) -> None:
    if not base_template_id:
        return
    now = datetime.utcnow()
    stmt = (
        pg_insert(PlayerItemCodex)
        .values(
            player_id=int(player_id),
            base_template_id=int(base_template_id),
            first_seen_at=now,
            seen_count=1,
        )
        .on_conflict_do_update(
            index_elements=["player_id", "base_template_id"],
            set_={
                "seen_count": PlayerItemCodex.seen_count + 1,
            },
        )
    )
    await session.execute(stmt)


async def mark_affix_seen(
    session: AsyncSession,
    player_id: int,
    *,
    catalog_kind: str,
    catalog_id: int,
) -> None:
    if not catalog_id:
        return
    stmt = (
        pg_insert(PlayerAffixCodex)
        .values(
            player_id=int(player_id),
            catalog_kind=str(catalog_kind),
            catalog_id=int(catalog_id),
            first_seen_at=datetime.utcnow(),
        )
        .on_conflict_do_nothing(
            index_elements=["player_id", "catalog_kind", "catalog_id"]
        )
    )
    await session.execute(stmt)


async def mark_affixes_from_inventory(
    session: AsyncSession, player_id: int, inv: m.InventoryItem
) -> None:
    affixes = list(getattr(inv, "affixes", None) or [])
    if not affixes and inv.id:
        res = await session.execute(
            select(m.InventoryAffix).where(m.InventoryAffix.inventory_item_id == int(inv.id))
        )
        affixes = list(res.scalars().all())

    for a in affixes:
        fam_id = getattr(a, "family_id", None)
        if fam_id is not None:
            await mark_affix_seen(
                session,
                player_id,
                catalog_kind=CATALOG_DIABLO,
                catalog_id=int(fam_id),
            )
            continue
        name = str(getattr(a, "name", "") or "").strip()
        if not name:
            continue
        leg = await session.scalar(
            select(m.Affix.id).where(func.lower(m.Affix.name) == name.lower()).limit(1)
        )
        if leg is not None:
            await mark_affix_seen(
                session,
                player_id,
                catalog_kind=CATALOG_LEGACY,
                catalog_id=int(leg),
            )


async def register_inventory_codex(
    session: AsyncSession, player_id: int | None, inv: m.InventoryItem
) -> None:
    """Record base item + affix discovery for a player from one inventory instance."""
    if not player_id or inv is None:
        return
    try:
        bt_id = await resolve_base_template_id(session, inv)
        if bt_id:
            await mark_item_seen(session, int(player_id), bt_id)
        await mark_affixes_from_inventory(session, int(player_id), inv)
    except Exception:
        logger.exception(
            "register_inventory_codex failed player_id=%s inv_id=%s",
            player_id,
            getattr(inv, "id", None),
        )
