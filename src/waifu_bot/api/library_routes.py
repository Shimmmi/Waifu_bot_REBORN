"""Library / Codex API: bestiary, item templates, and affix catalog.

Player discovery progress is joined server-side; hidden fields are redacted in the
response (anti-datamining).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.api.deps import get_db, get_player_id
from waifu_bot.db import models as m
from waifu_bot.db.models.item import PlayerAffixCodex, PlayerItemCodex
from waifu_bot.game import bestiary as bcfg
from waifu_bot.game.affix_display_names import (
    representative_affix_tier,
    resolve_prefix_name_ru,
    resolve_suffix_name_ru,
)
from waifu_bot.game.affix_effect_ui import effect_bonus_category, effect_stat_description_ru
from waifu_bot.services.item_art import derive_item_art_key, with_legendary_art_prefix
from waifu_bot.services.item_codex import CATALOG_DIABLO, CATALOG_LEGACY

logger = logging.getLogger(__name__)

router = APIRouter()

_HIDDEN_NAME = "???"
_HIDDEN_TYPE = "???"


def _tier_catalog() -> list[dict]:
    """Public description of every discovery tier (for the UI legend)."""
    out: list[dict] = []
    for t in bcfg.BESTIARY_TIERS:
        bonuses: list[str] = []
        if t.exp_pct:
            bonuses.append(f"+{round(t.exp_pct * 100)}% опыта")
        if t.gold_pct:
            bonuses.append(f"+{round(t.gold_pct * 100)}% золота")
        if t.dmg_pct:
            bonuses.append(f"+{round(t.dmg_pct * 100)}% урона")
        if t.dmg_taken_pct:
            bonuses.append(f"{round(t.dmg_taken_pct * 100)}% получаемого урона")
        reveals: list[str] = []
        if t.reveals_name:
            reveals.append("имя")
        if t.reveals_hp:
            reveals.append("HP")
        if t.reveals_type:
            reveals.append("тип")
        if t.reveals_damage:
            reveals.append("урон")
        if t.reveals_rewards:
            reveals.append("награды")
        if t.reveals_abilities:
            reveals.append("способности")
        if t.reveals_lore:
            reveals.append("лор")
        out.append(
            {
                "tier": t.tier,
                "kills_required": t.kills_required,
                "name": t.name,
                "bonuses": bonuses,
                "reveals": reveals,
                "title": t.title,
            }
        )
    return out


def _build_entry(tmpl: m.MonsterTemplate, kills: int, seen: bool, *, detailed: bool) -> dict:
    """Build a redacted bestiary entry for one template + player progress."""
    tier = bcfg.tier_for_kills(kills)
    reveal = bcfg.reveal_flags_for_tier(tier)
    bonuses = bcfg.cumulative_bonuses_for_tier(tier)
    next_threshold = bcfg.next_tier_threshold(kills)
    tier_def = bcfg.get_tier_def(tier)

    name = tmpl.name if reveal["name"] else _HIDDEN_NAME
    family = (tmpl.family or "") if reveal["type"] else None

    entry: dict = {
        "template_id": tmpl.id,
        "tier": tier,
        "tier_name": tier_def.name,
        "max_tier": bcfg.MAX_TIER,
        "kills": int(kills),
        "seen": bool(seen),
        "name": name,
        "name_known": reveal["name"],
        # Image hints: family/slug/monster-tier are needed to render art. These are
        # gated by "seen" (the monster has appeared in front of the player), not by
        # kill-tier: once encountered we show the real art, before that a silhouette.
        "family": (tmpl.family or "unknown") if seen else None,
        "slug": tmpl.slug if seen else None,
        "monster_tier": tmpl.tier,
        "has_image": bool(tmpl.has_image) if seen else False,
        "image_updated_at": (
            tmpl.image_updated_at.isoformat()
            if (seen and tmpl.image_updated_at)
            else None
        ),
        "emoji": tmpl.emoji if seen else None,
        # Where the monster can be found (always available for filtering/goals).
        "act_min": tmpl.act_min,
        "act_max": tmpl.act_max,
        # Progress to the next tier.
        "next_tier_kills": next_threshold,
        # Active per-monster bonuses at the current tier.
        "bonuses": {
            "dmg_pct": bonuses.dmg_pct,
            "dmg_taken_pct": bonuses.dmg_taken_pct,
            "exp_pct": bonuses.exp_pct,
            "gold_pct": bonuses.gold_pct,
        },
    }

    # Type/family text label (revealed at tier 3).
    entry["type"] = family if reveal["type"] else (_HIDDEN_TYPE if seen else None)

    # Stat curves are only revealed at the relevant tiers.
    if reveal["hp"]:
        entry["hp_base"] = tmpl.hp_base
        entry["hp_per_level"] = tmpl.hp_per_level
    if reveal["damage"]:
        entry["dmg_base"] = tmpl.dmg_base
        entry["dmg_per_level"] = tmpl.dmg_per_level
    if reveal["rewards"]:
        entry["exp_base"] = tmpl.exp_base
        entry["exp_per_level"] = tmpl.exp_per_level
        entry["gold_base"] = tmpl.gold_base
        entry["gold_per_level"] = tmpl.gold_per_level
        entry["level_min"] = tmpl.level_min
        entry["level_max"] = tmpl.level_max

    if detailed and reveal["lore"]:
        entry["lore_known"] = True

    return entry


@router.get("/library/bestiary", tags=["library"])
async def bestiary_catalog(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Full monster catalog with the player's (redacted) discovery progress."""
    try:
        templates = list(
            (await session.execute(select(m.MonsterTemplate))).scalars().all()
        )
        codex_rows = list(
            (
                await session.execute(
                    select(m.PlayerMonsterCodex).where(
                        m.PlayerMonsterCodex.player_id == player_id
                    )
                )
            )
            .scalars()
            .all()
        )
        kills_by_tmpl = {int(r.monster_template_id): int(r.kills) for r in codex_rows}
        seen_set = set(kills_by_tmpl.keys())

        entries = [
            _build_entry(
                t,
                kills_by_tmpl.get(int(t.id), 0),
                int(t.id) in seen_set,
                detailed=False,
            )
            for t in templates
        ]
        entries.sort(key=lambda e: (e["act_min"], e["template_id"]))

        total = len(templates)
        seen_count = len(seen_set)
        completed = sum(1 for e in entries if e["tier"] >= bcfg.MAX_TIER)
        return {
            "monsters": entries,
            "tiers": _tier_catalog(),
            "summary": {
                "total": total,
                "seen": seen_count,
                "completed": completed,
                "seen_pct": round(100.0 * seen_count / total) if total else 0,
            },
        }
    except Exception as e:
        logger.exception("Failed /library/bestiary for player_id=%s: %s", player_id, e)
        return {"monsters": [], "tiers": _tier_catalog(), "summary": {"total": 0, "seen": 0, "completed": 0, "seen_pct": 0}}


@router.get("/library/bestiary/{template_id}", tags=["library"])
async def bestiary_monster(
    template_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Detailed (redacted) page for a single monster template."""
    tmpl = await session.get(m.MonsterTemplate, int(template_id))
    if tmpl is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="monster_not_found")
    row = await session.get(m.PlayerMonsterCodex, (int(player_id), int(template_id)))
    kills = int(row.kills) if row is not None else 0
    seen = row is not None
    entry = _build_entry(tmpl, kills, seen, detailed=True)
    entry["tiers"] = _tier_catalog()
    return entry


def _slot_type_from_ibt(item_type: str | None, subtype: str | None) -> str:
    it = (item_type or "").lower()
    st = (subtype or "").lower()
    if it == "weapon":
        if st == "one_hand":
            return "weapon_1h"
        if st in {"two_hand", "bow", "staff"}:
            return "weapon_2h"
        if st in {"offhand", "orb"}:
            return "offhand"
        return "weapon_1h"
    if it == "armor":
        return "costume"
    if it == "ring":
        return "ring"
    if it == "amulet":
        return "amulet"
    return "other"


def _fmt_affix_range(value_min: int | float | None, value_max: int | float | None, is_percent: bool) -> str:
    vmin = int(value_min or 0)
    vmax = int(value_max or 0)
    if is_percent:
        return f"{vmin}–{vmax}%"
    return f"{vmin}–{vmax}"


def _row_get(row: object, key: str, default=None):
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row._mapping[key]  # type: ignore[attr-defined]
    except Exception:
        return getattr(row, key, default)


def _build_item_entry(row: object, seen: bool) -> dict:
    tid = int(_row_get(row, "id", 0) or 0)
    tier = int(_row_get(row, "tier", 1) or 1)
    item_type = str(_row_get(row, "item_type", "") or "")
    subtype = str(_row_get(row, "subtype", "") or "")
    base_name = str(_row_get(row, "name", "") or "")
    slot_type = _slot_type_from_ibt(item_type, subtype)
    weapon_type = subtype if item_type.lower() == "weapon" else None

    entry: dict = {
        "base_template_id": tid,
        "tier": tier,
        "seen": bool(seen),
        "name": base_name if seen else _HIDDEN_NAME,
        "name_known": bool(seen),
        "item_type": item_type if seen else None,
        "subtype": subtype if seen else None,
        "slot_type": slot_type if seen else None,
        "level_min": int(_row_get(row, "level_min", 0) or 0) if seen else None,
        "level_max": int(_row_get(row, "level_max", 0) or 0) if seen else None,
    }
    if seen:
        entry["art_key"] = derive_item_art_key(
            slot_type, weapon_type, base_name, display_name=base_name
        )
        dmg_min = int(_row_get(row, "dmg_min", 0) or 0)
        dmg_max = int(_row_get(row, "dmg_max", 0) or 0)
        if dmg_min > 0 or dmg_max > 0:
            entry["damage_min"] = dmg_min
            entry["damage_max"] = dmg_max
        atk = int(_row_get(row, "attack_speed", 0) or 0)
        if atk > 0:
            entry["attack_speed"] = atk
        armor = int(_row_get(row, "armor_base", 0) or 0)
        if armor > 0:
            entry["armor_base"] = armor
        st1 = _row_get(row, "stat1_type", None)
        if st1:
            entry["base_stat"] = str(st1)
            entry["base_stat_value"] = int(_row_get(row, "stat1_value", 0) or 0)
        flavor = str(_row_get(row, "flavor_ru", "") or "").strip()
        if flavor:
            entry["flavor_ru"] = flavor
    return entry


@router.get("/library/items", tags=["library"])
async def items_catalog(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Base item templates with per-player discovery (seen / hidden)."""
    try:
        templates = list(
            (
                await session.execute(
                    text("SELECT * FROM item_base_templates ORDER BY tier, name")
                )
            )
            .mappings()
            .all()
        )
        codex_rows = list(
            (
                await session.execute(
                    select(PlayerItemCodex).where(PlayerItemCodex.player_id == player_id)
                )
            )
            .scalars()
            .all()
        )
        seen_set = {int(r.base_template_id) for r in codex_rows}
        entries = [_build_item_entry(t, int(t["id"]) in seen_set) for t in templates]
        total = len(entries)
        seen_count = len(seen_set)
        return {
            "items": entries,
            "summary": {
                "total": total,
                "seen": seen_count,
                "seen_pct": round(100.0 * seen_count / total) if total else 0,
            },
        }
    except Exception as e:
        logger.exception("Failed /library/items for player_id=%s: %s", player_id, e)
        return {"items": [], "summary": {"total": 0, "seen": 0, "seen_pct": 0}}


@router.get("/library/items/{base_template_id}", tags=["library"])
async def item_detail(
    base_template_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    row = (
        await session.execute(
            text("SELECT * FROM item_base_templates WHERE id = :id"),
            {"id": int(base_template_id)},
        )
    ).mappings().first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="item_not_found")
    codex = await session.get(PlayerItemCodex, (int(player_id), int(base_template_id)))
    seen = codex is not None
    return _build_item_entry(row, seen)


async def build_affix_catalog_entries(
    session: AsyncSession,
    *,
    seen_legacy: set[int],
    seen_diablo: set[int],
) -> list[dict]:
    """Affix catalog rows; pass empty sets to hide all, or all ids for admin full catalog."""
    entries: list[dict] = []
    legacy = list((await session.execute(select(m.Affix).order_by(m.Affix.name))).scalars().all())
    for aff in legacy:
        seen = int(aff.id) in seen_legacy
        stat = str(aff.stat or "")
        desc = effect_stat_description_ru(stat)
        cat_id, cat_label = effect_bonus_category(stat)
        name_ru = aff.name if seen else _HIDDEN_NAME
        entries.append(
            {
                "catalog_kind": CATALOG_LEGACY,
                "catalog_id": int(aff.id),
                "seen": seen,
                "name": name_ru,
                "name_ru": name_ru,
                "kind": aff.kind if seen else None,
                "stat": stat if seen else None,
                "bonus_category": cat_id,
                "bonus_category_label": cat_label,
                "description_ru": desc if seen else None,
                "value_min": int(aff.value_min) if seen else None,
                "value_max": int(aff.value_max) if seen else None,
                "is_percent": bool(aff.is_percent) if seen else None,
                "range_label": (
                    _fmt_affix_range(aff.value_min, aff.value_max, aff.is_percent)
                    if seen
                    else None
                ),
                "tier": int(aff.tier) if seen else None,
            }
        )

    families = list(
        (await session.execute(select(m.AffixFamily).order_by(m.AffixFamily.family_id))).scalars().all()
    )
    for fam in families:
        seen = int(fam.id) in seen_diablo
        tier_rows = list(
            (
                await session.execute(
                    select(m.AffixFamilyTier).where(m.AffixFamilyTier.family_id == fam.id)
                )
            )
            .scalars()
            .all()
        )
        vmin = vmax = None
        if tier_rows:
            mins = [float(t.value_min) for t in tier_rows if t.value_min is not None]
            maxs = [float(t.value_max) for t in tier_rows if t.value_max is not None]
            if mins:
                vmin = int(min(mins))
            if maxs:
                vmax = int(max(maxs))
        effect_key = str(fam.effect_key or "")
        cat_id, cat_label = effect_bonus_category(effect_key)
        is_pct = "pct" in effect_key.lower() or "percent" in effect_key.lower()
        rep_tier = representative_affix_tier(tier_rows)
        kind = str(fam.kind or "")
        if seen:
            fid = str(fam.family_id or "")
            if kind in ("suffix",):
                name_ru = resolve_suffix_name_ru(fid, rep_tier)
            else:
                name_ru = resolve_prefix_name_ru(effect_key, rep_tier, family_id=fid or None)
        else:
            name_ru = _HIDDEN_NAME
        entries.append(
            {
                "catalog_kind": CATALOG_DIABLO,
                "catalog_id": int(fam.id),
                "seen": seen,
                "name": name_ru,
                "name_ru": name_ru,
                "kind": fam.kind if seen else None,
                "stat": effect_key if seen else None,
                "bonus_category": cat_id,
                "bonus_category_label": cat_label,
                "description_ru": effect_stat_description_ru(effect_key) if seen else None,
                "value_min": vmin if seen else None,
                "value_max": vmax if seen else None,
                "is_percent": is_pct if seen else None,
                "range_label": (
                    _fmt_affix_range(vmin, vmax, is_pct) if seen and vmin is not None else None
                ),
                "family_id": fam.family_id if seen else None,
            }
        )

    entries.sort(key=lambda e: (e.get("kind") or "", e.get("name") or ""))
    return entries


def build_admin_template_entry(row: object) -> dict:
    """Full template row for admin spawn UI (no codex redaction)."""
    entry = _build_item_entry(row, seen=True)
    raw_leg = _row_get(row, "legendary_bonus_ids", None) or []
    try:
        leg_ids = [int(x) for x in raw_leg if x is not None]
    except (TypeError, ValueError):
        leg_ids = []
    entry["legendary_bonus_ids"] = leg_ids
    entry["base_grade"] = int(_row_get(row, "base_grade", 0) or 0)
    entry["has_curated_legendary"] = len(leg_ids) > 0
    leg_name = str(_row_get(row, "legendary_name_ru", "") or "").strip()
    entry["legendary_name_ru"] = leg_name or None
    base_art = str(entry.get("art_key") or "").strip()
    if base_art and (leg_ids or leg_name):
        entry["legendary_art_key"] = with_legendary_art_prefix(base_art)
    return entry


@router.get("/library/affixes", tags=["library"])
async def affixes_catalog(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Affix / suffix catalog (legacy + diablo families) with discovery."""
    try:
        codex_rows = list(
            (
                await session.execute(
                    select(PlayerAffixCodex).where(PlayerAffixCodex.player_id == player_id)
                )
            )
            .scalars()
            .all()
        )
        seen_legacy = {
            int(r.catalog_id)
            for r in codex_rows
            if r.catalog_kind == CATALOG_LEGACY
        }
        seen_diablo = {
            int(r.catalog_id)
            for r in codex_rows
            if r.catalog_kind == CATALOG_DIABLO
        }

        entries = await build_affix_catalog_entries(
            session, seen_legacy=seen_legacy, seen_diablo=seen_diablo
        )
        total = len(entries)
        seen_count = sum(1 for e in entries if e.get("seen"))
        return {
            "affixes": entries,
            "summary": {
                "total": total,
                "seen": seen_count,
                "seen_pct": round(100.0 * seen_count / total) if total else 0,
            },
        }
    except Exception as e:
        logger.exception("Failed /library/affixes for player_id=%s: %s", player_id, e)
        return {"affixes": [], "summary": {"total": 0, "seen": 0, "seen_pct": 0}}
