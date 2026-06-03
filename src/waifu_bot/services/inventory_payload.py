"""Shared inventory item serialization for API and Armory."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, text, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db import models as m
from waifu_bot.game.affix_effect_ui import effect_stat_description_ru
from waifu_bot.game.item_display_name import compose_item_display_name_ru
from waifu_bot.game.item_secondary import (
    attach_resolved_attrs,
    effective_fraction_combat,
    resolve_item_secondaries,
    template_row_from_mapping,
)
from waifu_bot.services.enchanting import get_effective_params
from waifu_bot.services.item_art import derive_image_key, derive_item_art_key, enrich_items_with_image_urls
from waifu_bot.services.passive_skills import normalize_passive_level_affix_value
from waifu_bot.game.legendary_bonuses.loader import fetch_legendary_bonus_payloads


async def enrich_inventory_items_with_template_stats(
    session: AsyncSession,
    items: list[m.InventoryItem] | None,
) -> None:
    if not items:
        return
    keys: set[tuple[str, int]] = set()
    for inv in items:
        item_name = str(getattr(getattr(inv, "item", None), "name", "") or "").strip()
        tier = int(getattr(inv, "tier", None) or getattr(getattr(inv, "item", None), "tier", None) or 0)
        if item_name and tier > 0:
            keys.add((item_name, tier))
    stats_map: dict[tuple[str, int], Any] = {}
    if keys:
        try:
            stmt = (
                select(
                    text("name"),
                    text("tier"),
                    text("armor_base"),
                    text("secondary_bonus_type"),
                    text("secondary_bonus_value"),
                )
                .select_from(text("item_base_templates"))
                .where(tuple_(text("name"), text("tier")).in_(list(keys)))
            )
            rows = (await session.execute(stmt)).all()
            for row in rows:
                stats_map[(str(getattr(row, "name", "") or ""), int(getattr(row, "tier", 0) or 0))] = row
        except Exception:
            stats_map = {}

    for inv in items:
        item_name = str(getattr(getattr(inv, "item", None), "name", "") or "").strip()
        tier = int(getattr(inv, "tier", None) or getattr(getattr(inv, "item", None), "tier", None) or 0)
        tpl_row = stats_map.get((item_name, tier))
        template = template_row_from_mapping(tpl_row) if tpl_row else None
        resolved = resolve_item_secondaries(inv, template)
        attach_resolved_attrs(inv, resolved)


def _fallback_base_name_ru(inv: m.InventoryItem) -> str:
    st = (inv.slot_type or "").lower()
    wt = (inv.weapon_type or "").lower()
    if "ring" in st:
        return "Кольцо"
    if "amulet" in st:
        return "Амулет"
    if "costume" in st or "armor" in st:
        return "Доспех"
    if "offhand" in st:
        if wt == "orb" or "сфера" in (inv.item.name if inv.item else "").lower():
            return "Сфера"
        return "Щит"
    if "weapon" in st:
        if "axe" in wt:
            return "Топор"
        if "sword" in wt:
            return "Меч"
        if "bow" in wt:
            return "Лук"
        if "staff" in wt or "wand" in wt:
            return "Посох"
        if "dagger" in wt:
            return "Кинжал"
        return "Оружие"
    return "Предмет"


def serialize_inventory_item(
    inv: m.InventoryItem,
    *,
    legendary_bonuses: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    affixes = [
        {
            "name": a.name,
            "stat": a.stat,
            "value": normalize_passive_level_affix_value(a.stat, a.value),
            "is_percent": a.is_percent,
            "kind": a.kind,
            "tier": a.tier,
            "description": effect_stat_description_ru(a.stat) or None,
        }
        for a in (inv.affixes or [])
    ]

    base_name, display_name = compose_item_display_name_ru(inv)

    image_key = derive_image_key(inv.slot_type, inv.weapon_type, display_name)
    art_key = derive_item_art_key(
        inv.slot_type, inv.weapon_type, base_name, display_name=display_name
    )

    ab = int(getattr(inv, "_armor_base", 0) or 0)
    resolved = getattr(inv, "_resolved_secondaries", None) or resolve_item_secondaries(inv, None)
    frac_type, frac_val = effective_fraction_combat(inv, resolved)
    eff = get_effective_params(inv, armor_base=ab, secondary_bonus_value=frac_val or 0.0)

    return {
        "id": inv.id,
        "name": base_name,
        "display_name": display_name,
        "rarity": inv.rarity,
        "level": inv.level,
        "tier": inv.tier,
        "equipment_slot": inv.equipment_slot,
        "damage_min": inv.damage_min,
        "damage_max": inv.damage_max,
        "damage_min_effective": eff.get("damage_min"),
        "damage_max_effective": eff.get("damage_max"),
        "attack_speed": inv.attack_speed,
        "attack_type": inv.attack_type,
        "weapon_type": inv.weapon_type,
        "base_stat": inv.base_stat,
        "base_stat_value": inv.base_stat_value,
        "armor_base": ab or None,
        "armor_effective": int(eff.get("armor", 0) or 0) or None,
        "secondary_bonus_type": getattr(inv, "_secondary_bonus_type", None),
        "secondary_bonus_value": float(getattr(inv, "_secondary_bonus_value", 0.0) or 0.0) or None,
        "secondary_fraction_type": frac_type,
        "secondary_fraction_value": float(resolved.fraction_value) or None,
        "secondary_fraction_effective": float(frac_val) if frac_val else None,
        "secondary_awakened": bool(getattr(inv, "_secondary_awakened", False)),
        "secondary_bonus_effective": float(eff.get("secondary", 0.0) or 0.0) or None,
        "enchant_level": int(getattr(inv, "enchant_level", 0) or 0),
        "enchant_dmg_step": int(getattr(inv, "enchant_dmg_step", 0) or 0),
        "enchant_arm_step": int(getattr(inv, "enchant_arm_step", 0) or 0),
        "enchant_sec_step": float(getattr(inv, "enchant_sec_step", 0.0) or 0.0),
        "is_broken": bool(getattr(inv, "is_broken", False)),
        "is_legendary": inv.is_legendary,
        "legendary_bonuses": legendary_bonuses or [],
        "requirements": inv.requirements,
        "affixes": affixes,
        "slot_type": inv.slot_type,
        "image_key": image_key,
        "art_key": art_key,
        "image_url": None,
    }


async def build_inventory_payloads(
    session: AsyncSession,
    items: list[m.InventoryItem],
) -> list[dict[str, Any]]:
    if not items:
        return []
    await enrich_inventory_items_with_template_stats(session, items)
    bonus_map = await fetch_legendary_bonus_payloads(session, items)
    payloads = [
        serialize_inventory_item(inv, legendary_bonuses=bonus_map.get(int(inv.id), []))
        for inv in items
    ]
    await enrich_items_with_image_urls(session, payloads)
    return payloads
