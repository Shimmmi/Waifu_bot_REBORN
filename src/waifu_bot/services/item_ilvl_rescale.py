"""Idempotent rescale of existing Dungeon+ items onto the ilvl bonus curve."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from waifu_bot.db import models as m
from types import SimpleNamespace

from sqlalchemy import text

from waifu_bot.game.item_ilvl_scaling import (
    CURRENT_SCALE_VER,
    PRIMARY_STATS,
    apply_flat_to_int,
    apply_template_fraction,
    item_scale_ilvl,
    primary_catchup_scaled,
    scale_affix_raw,
    scaled_template_armor,
    should_rescale_inventory,
)
from waifu_bot.services.enchanting import apply_enchant_steps_to_inventory_item, calculate_enchant_steps
from waifu_bot.services.enchanting import apply_enchant_steps_to_inventory_item

logger = logging.getLogger(__name__)


def rescale_legacy_plus_item(inv: Any, *, scale_ilvl: int | None = None) -> bool:
    """Rewrite stored flats/% on one plus item. Returns True if numbers changed."""
    if not should_rescale_inventory(inv):
        return False
    silvl = int(scale_ilvl) if scale_ilvl is not None else item_scale_ilvl(inv)
    if silvl <= 0:
        inv.ilvl_stat_scale_ver = CURRENT_SCALE_VER
        return False

    if getattr(inv, "base_stat_value", None) is not None:
        inv.base_stat_value = apply_flat_to_int(int(inv.base_stat_value), silvl)
    if getattr(inv, "damage_min", None) is not None:
        inv.damage_min = apply_flat_to_int(int(inv.damage_min), silvl)
    if getattr(inv, "damage_max", None) is not None:
        inv.damage_max = apply_flat_to_int(int(inv.damage_max), silvl)
    item = getattr(inv, "item", None)
    if item is not None and getattr(item, "damage", None) is not None:
        item.damage = inv.damage_max if getattr(inv, "damage_max", None) is not None else inv.damage_min

    for aff in getattr(inv, "affixes", None) or []:
        stat = str(getattr(aff, "stat", "") or "").strip().lower()
        try:
            raw = int(float(getattr(aff, "value", 0) or 0))
        except (TypeError, ValueError):
            continue
        tier = getattr(aff, "affix_tier", None)
        if tier is None:
            tier = getattr(aff, "tier", None)
        try:
            affix_tier = int(tier) if tier is not None else 1
        except (TypeError, ValueError):
            affix_tier = 1
        if stat in PRIMARY_STATS and affix_tier <= 2:
            aff.value = str(primary_catchup_scaled(raw, affix_tier, silvl))
        else:
            aff.value = str(scale_affix_raw(stat, raw, silvl))

    frac = float(getattr(inv, "secondary_fraction_value", 0.0) or 0.0)
    if frac > 0:
        inv.secondary_fraction_value = apply_template_fraction(frac, silvl)

    inv.ilvl_stat_scale_ver = CURRENT_SCALE_VER
    return True


async def rescale_legacy_plus_items(session: AsyncSession, *, limit: int | None = None) -> int:
    """Load plus/power_rank items with ver < current and rescale them."""
    stmt = (
        select(m.InventoryItem)
        .options(selectinload(m.InventoryItem.affixes), selectinload(m.InventoryItem.item))
        .where(m.InventoryItem.ilvl_stat_scale_ver < CURRENT_SCALE_VER)
        .where(or_(m.InventoryItem.plus_level_source > 0, m.InventoryItem.power_rank > 0))
    )
    if limit is not None:
        stmt = stmt.limit(int(limit))
    items = list((await session.scalars(stmt)).all())
    changed = 0
    for inv in items:
        if not rescale_legacy_plus_item(inv):
            continue
        try:
            await apply_enchant_steps_to_inventory_item(session, inv)
        except Exception:
            logger.exception("enchant step recalc failed inventory_item_id=%s", getattr(inv, "id", None))
        changed += 1
    return changed


def rescale_legacy_plus_items_on_bind(bind: Any) -> int:
    """Sync remake on an Alembic/SQLAlchemy connection (same transaction as the column add)."""
    rows = bind.execute(
        text(
            """
            SELECT inv.id,
                   inv.base_stat_value,
                   inv.damage_min,
                   inv.damage_max,
                   inv.power_rank,
                   inv.plus_level_source,
                   inv.secondary_fraction_value,
                   inv.ilvl_stat_scale_ver,
                   inv.item_id,
                   i.damage AS item_damage,
                   COALESCE(ibt.armor_base, 0) AS armor_base
            FROM inventory_items inv
            LEFT JOIN items i ON i.id = inv.item_id
            LEFT JOIN item_base_templates ibt
              ON ibt.name = i.name
             AND ibt.tier = COALESCE(inv.tier, i.tier)
            WHERE COALESCE(inv.ilvl_stat_scale_ver, 0) < :ver
              AND (inv.plus_level_source > 0 OR inv.power_rank > 0)
            """
        ),
        {"ver": CURRENT_SCALE_VER},
    ).mappings().all()

    changed = 0
    for row in rows:
        aff_rows = list(
            bind.execute(
                text(
                    """
                    SELECT id, stat, value, affix_tier, tier
                    FROM inventory_affixes
                    WHERE inventory_item_id = :iid
                    """
                ),
                {"iid": int(row["id"])},
            ).mappings().all()
        )
        affixes = [
            SimpleNamespace(
                id=int(a["id"]),
                stat=a["stat"],
                value=a["value"],
                affix_tier=a["affix_tier"],
                tier=a["tier"],
            )
            for a in aff_rows
        ]
        item = SimpleNamespace(damage=row["item_damage"])
        inv = SimpleNamespace(
            id=int(row["id"]),
            base_stat_value=row["base_stat_value"],
            damage_min=row["damage_min"],
            damage_max=row["damage_max"],
            power_rank=row["power_rank"],
            plus_level_source=row["plus_level_source"],
            secondary_fraction_value=row["secondary_fraction_value"],
            ilvl_stat_scale_ver=row["ilvl_stat_scale_ver"],
            affixes=affixes,
            item=item,
        )
        if not rescale_legacy_plus_item(inv):
            continue
        armor = scaled_template_armor(row["armor_base"], inv)
        steps = calculate_enchant_steps(
            inv.damage_min,
            inv.damage_max,
            armor,
            float(inv.secondary_fraction_value or 0.0),
        )
        bind.execute(
            text(
                """
                UPDATE inventory_items
                SET base_stat_value = :bsv,
                    damage_min = :dmin,
                    damage_max = :dmax,
                    secondary_fraction_value = :frac,
                    enchant_dmg_step = :ed,
                    enchant_arm_step = :ea,
                    enchant_sec_step = :es,
                    ilvl_stat_scale_ver = :ver
                WHERE id = :id
                """
            ),
            {
                "bsv": inv.base_stat_value,
                "dmin": inv.damage_min,
                "dmax": inv.damage_max,
                "frac": float(inv.secondary_fraction_value or 0.0),
                "ed": int(steps["enchant_dmg_step"]),
                "ea": int(steps["enchant_arm_step"]),
                "es": float(steps["enchant_sec_step"]),
                "ver": CURRENT_SCALE_VER,
                "id": int(inv.id),
            },
        )
        if row["item_id"] is not None:
            bind.execute(
                text("UPDATE items SET damage = :dmg WHERE id = :id"),
                {"dmg": item.damage, "id": int(row["item_id"])},
            )
        for aff in affixes:
            bind.execute(
                text("UPDATE inventory_affixes SET value = :val WHERE id = :id"),
                {"val": str(aff.value), "id": int(aff.id)},
            )
        changed += 1
    return changed
