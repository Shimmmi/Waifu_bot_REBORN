"""Поштучная атрибуция брони, снижения урона и уклонения для журнала боя."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import MainWaifu
from waifu_bot.game.constants import (
    DODGE_CHANCE_CAP,
    END_DAMAGE_REDUCTION_CAP,
    END_DAMAGE_REDUCTION_COEFF,
)
from waifu_bot.game.formulas import calculate_damage_reduction, calculate_dodge_chance
from waifu_bot.services.passive_skills import get_passive_contributions_for_log

TOTAL_REDUCE_CAP = 0.90
INCOMING_CONTRIB_MAX = 40


def _contrib_row(
    *,
    source: str,
    label_ru: str,
    pct_add: float | None = None,
    flat_add: float | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "kind": "contrib",
        "source": source[:120],
        "label_ru": label_ru[:220],
    }
    if pct_add is not None:
        row["pct_add"] = round(float(pct_add), 6)
    if flat_add is not None:
        row["flat_add"] = round(float(flat_add), 4)
    if meta:
        row["meta"] = meta
    return row


def sum_pct_contribs(contribs: list[dict[str, Any]]) -> float:
    return sum(float(c.get("pct_add") or 0) for c in contribs if c.get("kind") == "contrib")


def apply_total_reduce_cap(contribs: list[dict[str, Any]], *, cap: float = TOTAL_REDUCE_CAP) -> tuple[float, list[dict[str, Any]]]:
    """Сумма pct_add из contrib-строк и опциональный шаг cap."""
    raw_sum = sum_pct_contribs(contribs)
    applied = min(cap, max(0.0, raw_sum))
    extra: list[dict[str, Any]] = []
    if raw_sum > applied + 1e-9:
        extra.append(
            {
                "kind": "cap",
                "source": "cap:total_reduce_90",
                "label_ru": (
                    f"Потолок снижения входящего {cap * 100:.0f}%: "
                    f"сумма источников {raw_sum * 100:.1f}%, учтено {applied * 100:.1f}%, "
                    f"отброшено {(raw_sum - applied) * 100:.1f}%"
                ),
                "pct_add": applied,
                "meta": {"raw_sum": raw_sum, "cap": cap},
            }
        )
    return applied, extra


async def collect_endurance_dmg_reduce_contrib(waifu: MainWaifu, main_stats_flat: int) -> dict[str, Any]:
    end_eff = int(getattr(waifu, "endurance", 10) or 10) + int(main_stats_flat or 0)
    raw_pct = float(end_eff) * END_DAMAGE_REDUCTION_COEFF
    end_reduce = float(calculate_damage_reduction(end_eff))
    capped_note = ""
    if raw_pct > END_DAMAGE_REDUCTION_CAP + 1e-9:
        capped_note = f", сырой {raw_pct * 100:.2f}% → потолок ВЫН {END_DAMAGE_REDUCTION_CAP * 100:.0f}%"
    return _contrib_row(
        source="stat:endurance",
        label_ru=f"ВЫН (эфф. {end_eff}): +{end_reduce * 100:.2f}% к пулу снижения{capped_note}",
        pct_add=end_reduce,
        meta={"endurance_eff": end_eff, "raw_pct": raw_pct},
    )


async def collect_passive_dmg_reduce_contribs(
    session: AsyncSession, player_id: int
) -> list[dict[str, Any]]:
    rows = await get_passive_contributions_for_log(session, player_id)
    out: list[dict[str, Any]] = []
    for r in rows:
        et = str(r.get("effect_type") or "")
        if et not in ("dmg_reduce_pct", "int_dmg_reduce"):
            continue
        v = float(r.get("value") or 0)
        nid = str(r.get("node_id") or "")
        name = str(r.get("name") or nid)
        lvl = int(r.get("level") or 0)
        if et == "int_dmg_reduce":
            label = f"Пассив «{name}» (ур. {lvl}): рун. броня +{v * 100:.1f}% к пулу снижения"
            src = f"passive:{nid}:int_dmg_reduce"
        else:
            label = f"Пассив «{name}» (ур. {lvl}): снижение урона +{v * 100:.1f}% к пулу"
            src = f"passive:{nid}:dmg_reduce_pct"
        out.append(_contrib_row(source=src, label_ru=label, pct_add=v, meta={"node_id": nid, "level": lvl}))
    return out


async def collect_gear_dmg_reduce_contribs(session: AsyncSession, player_id: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT
                        inv.id AS inv_id,
                        inv.equipment_slot AS slot,
                        i.name AS item_name,
                        COALESCE(ibt.secondary_bonus_type, '') AS sec_type,
                        COALESCE(ibt.secondary_bonus_value, 0.0) AS sec_base,
                        COALESCE(inv.enchant_sec_step, 0.0) AS sec_step,
                        COALESCE(inv.enchant_level, 0) AS enchant_level,
                        COALESCE(inv.is_broken, false) AS is_broken
                    FROM inventory_items inv
                    JOIN items i ON i.id = inv.item_id
                    JOIN item_base_templates ibt
                      ON ibt.name = i.name
                     AND ibt.tier = COALESCE(inv.tier, i.tier)
                    WHERE inv.player_id = :pid
                      AND inv.equipment_slot IS NOT NULL
                    """
                ),
                {"pid": int(player_id)},
            )
        ).all()
        for row in rows:
            sec_type = str(getattr(row, "sec_type", "") or "").strip().lower()
            if sec_type != "dmg_reduce_pct":
                continue
            e = 0 if bool(getattr(row, "is_broken", False)) else int(getattr(row, "enchant_level", 0) or 0)
            sec_val = float(getattr(row, "sec_base", 0) or 0) + float(getattr(row, "sec_step", 0) or 0) * e
            if sec_val <= 0:
                continue
            slot = str(getattr(row, "slot", "") or "slot")
            item_name = str(getattr(row, "item_name", "") or "предмет")
            out.append(
                _contrib_row(
                    source=f"gear:{slot}:{item_name}"[:120],
                    label_ru=f"Экипировка [{slot}] «{item_name}»: +{sec_val * 100:.2f}% к пулу снижения",
                    pct_add=sec_val,
                    meta={"inventory_id": int(getattr(row, "inv_id", 0) or 0), "slot": slot},
                )
            )
    except Exception:
        pass
    try:
        aff_rows = (
            await session.execute(
                text(
                    """
                    SELECT inv.id AS inv_id, inv.equipment_slot AS slot, i.name AS item_name,
                           LOWER(TRIM(ia.stat)) AS stat, ia.value
                    FROM inventory_affixes ia
                    JOIN inventory_items inv ON inv.id = ia.inventory_item_id
                    JOIN items i ON i.id = inv.item_id
                    WHERE inv.player_id = :pid
                      AND inv.equipment_slot IS NOT NULL
                      AND LOWER(TRIM(ia.stat)) = 'dmg_reduce_pct'
                    """
                ),
                {"pid": int(player_id)},
            )
        ).all()
        for row in aff_rows:
            try:
                vi = int(float(getattr(row, "value", 0) or 0))
            except (ValueError, TypeError):
                continue
            frac = float(vi) / 10000.0
            if frac <= 0:
                continue
            inv_id = int(getattr(row, "inv_id", 0) or 0)
            slot = str(getattr(row, "slot", "") or "slot")
            item_name = str(getattr(row, "item_name", "") or "предмет")
            out.append(
                _contrib_row(
                    source=f"affix:{inv_id}:dmg_reduce_pct",
                    label_ru=f"Аффикс [{slot}] «{item_name}»: +{frac * 100:.2f}% к пулу снижения",
                    pct_add=frac,
                    meta={"inventory_id": inv_id, "affix_value": vi},
                )
            )
    except Exception:
        pass
    return out


async def collect_all_dmg_reduce_contribs(
    session: AsyncSession,
    player_id: int,
    waifu: MainWaifu,
    *,
    main_stats_flat: int = 0,
) -> list[dict[str, Any]]:
    contribs: list[dict[str, Any]] = []
    contribs.append(await collect_endurance_dmg_reduce_contrib(waifu, main_stats_flat))
    contribs.extend(await collect_passive_dmg_reduce_contribs(session, player_id))
    contribs.extend(await collect_gear_dmg_reduce_contribs(session, player_id))
    return contribs[:INCOMING_CONTRIB_MAX]


async def collect_armor_slot_contribs(session: AsyncSession, player_id: int) -> list[dict[str, Any]]:
    """Плоская броня по слотам (до пассивного armor_pct)."""
    out: list[dict[str, Any]] = []
    try:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT
                        inv.equipment_slot AS slot,
                        i.name AS item_name,
                        COALESCE(ibt.armor_base, 0) AS armor_base,
                        COALESCE(inv.enchant_arm_step, 0) AS arm_step,
                        COALESCE(inv.enchant_level, 0) AS enchant_level,
                        COALESCE(inv.is_broken, false) AS is_broken
                    FROM inventory_items inv
                    JOIN items i ON i.id = inv.item_id
                    JOIN item_base_templates ibt
                      ON ibt.name = i.name
                     AND ibt.tier = COALESCE(inv.tier, i.tier)
                    WHERE inv.player_id = :pid
                      AND inv.equipment_slot IS NOT NULL
                    """
                ),
                {"pid": int(player_id)},
            )
        ).all()
        for row in rows:
            e = 0 if bool(getattr(row, "is_broken", False)) else int(getattr(row, "enchant_level", 0) or 0)
            armor = float(getattr(row, "armor_base", 0) or 0) + float(int(getattr(row, "arm_step", 0) or 0) * e)
            if armor <= 0:
                continue
            slot = str(getattr(row, "slot", "") or "slot")
            item_name = str(getattr(row, "item_name", "") or "предмет")
            out.append(
                _contrib_row(
                    source=f"gear:{slot}:{item_name}:armor"[:120],
                    label_ru=f"Броня [{slot}] «{item_name}»: +{int(armor)}",
                    flat_add=armor,
                    meta={"slot": slot},
                )
            )
    except Exception:
        pass
    return out


async def collect_passive_armor_pct_contribs(
    session: AsyncSession, player_id: int
) -> list[dict[str, Any]]:
    rows = await get_passive_contributions_for_log(session, player_id)
    out: list[dict[str, Any]] = []
    for r in rows:
        if str(r.get("effect_type") or "") != "armor_pct":
            continue
        v = float(r.get("value") or 0)
        nid = str(r.get("node_id") or "")
        name = str(r.get("name") or nid)
        lvl = int(r.get("level") or 0)
        out.append(
            _contrib_row(
                source=f"passive:{nid}:armor_pct",
                label_ru=f"Пассив «{name}» (ур. {lvl}): броня ×{1.0 + v:.3f}",
                pct_add=v,
                meta={"node_id": nid, "mult_factor": 1.0 + v},
            )
        )
    return out


async def collect_evade_chance_contribs(
    session: AsyncSession,
    player_id: int,
    waifu: MainWaifu,
    *,
    eff_agility: int,
    eff_luck: int,
) -> list[dict[str, Any]]:
    """Вклады в шанс уклонения (информативно; итог capped в бою)."""
    base = float(calculate_dodge_chance(int(eff_agility), int(eff_luck)))
    out: list[dict[str, Any]] = [
        _contrib_row(
            source="stat:agility_luck_dodge",
            label_ru=f"ЛОВ/УДЧ: базовый шанс уклонения {base * 100:.2f}%",
            pct_add=base,
            meta={"agility": eff_agility, "luck": eff_luck},
        )
    ]
    rows = await get_passive_contributions_for_log(session, player_id)
    for r in rows:
        et = str(r.get("effect_type") or "")
        if et not in ("evade_pct", "full_evade_chance"):
            continue
        v = float(r.get("value") or 0)
        nid = str(r.get("node_id") or "")
        name = str(r.get("name") or nid)
        lvl = int(r.get("level") or 0)
        if et == "full_evade_chance":
            out.append(
                _contrib_row(
                    source=f"passive:{nid}:full_evade",
                    label_ru=f"Пассив «{name}» (ур. {lvl}): полное уклонение {v * 100:.1f}% (отдельный бросок)",
                    pct_add=v,
                )
            )
        else:
            out.append(
                _contrib_row(
                    source=f"passive:{nid}:evade_pct",
                    label_ru=f"Пассив «{name}» (ур. {lvl}): +{v * 100:.1f}% к шансу уклонения",
                    pct_add=v,
                )
            )
    try:
        aff_rows = (
            await session.execute(
                text(
                    """
                    SELECT inv.id AS inv_id, inv.equipment_slot AS slot, i.name AS item_name,
                           ia.value
                    FROM inventory_affixes ia
                    JOIN inventory_items inv ON inv.id = ia.inventory_item_id
                    JOIN items i ON i.id = inv.item_id
                    WHERE inv.player_id = :pid
                      AND inv.equipment_slot IS NOT NULL
                      AND LOWER(TRIM(ia.stat)) = 'evade_pct'
                    """
                ),
                {"pid": int(player_id)},
            )
        ).all()
        for row in aff_rows:
            try:
                vi = int(float(getattr(row, "value", 0) or 0))
            except (ValueError, TypeError):
                continue
            frac = float(vi) / 10000.0
            if frac <= 0:
                continue
            inv_id = int(getattr(row, "inv_id", 0) or 0)
            slot = str(getattr(row, "slot", "") or "slot")
            item_name = str(getattr(row, "item_name", "") or "предмет")
            out.append(
                _contrib_row(
                    source=f"affix:{inv_id}:evade_pct",
                    label_ru=f"Аффикс [{slot}] «{item_name}»: +{frac * 100:.2f}% уклонения",
                    pct_add=frac,
                )
            )
    except Exception:
        pass
    try:
        gear_rows = (
            await session.execute(
                text(
                    """
                    SELECT inv.equipment_slot AS slot, i.name AS item_name,
                           COALESCE(ibt.secondary_bonus_value, 0.0) AS sec_base,
                           COALESCE(inv.enchant_sec_step, 0.0) AS sec_step,
                           COALESCE(inv.enchant_level, 0) AS enchant_level,
                           COALESCE(inv.is_broken, false) AS is_broken
                    FROM inventory_items inv
                    JOIN items i ON i.id = inv.item_id
                    JOIN item_base_templates ibt
                      ON ibt.name = i.name AND ibt.tier = COALESCE(inv.tier, i.tier)
                    WHERE inv.player_id = :pid
                      AND inv.equipment_slot IS NOT NULL
                      AND ibt.secondary_bonus_type = 'evade_pct'
                    """
                ),
                {"pid": int(player_id)},
            )
        ).all()
        for row in gear_rows:
            e = 0 if bool(getattr(row, "is_broken", False)) else int(getattr(row, "enchant_level", 0) or 0)
            sec_val = float(getattr(row, "sec_base", 0) or 0) + float(getattr(row, "sec_step", 0) or 0) * e
            if sec_val <= 0:
                continue
            slot = str(getattr(row, "slot", "") or "slot")
            item_name = str(getattr(row, "item_name", "") or "предмет")
            out.append(
                _contrib_row(
                    source=f"gear:{slot}:{item_name}:evade"[:120],
                    label_ru=f"Экипировка [{slot}] «{item_name}»: +{sec_val * 100:.2f}% уклонения",
                    pct_add=sec_val,
                )
            )
    except Exception:
        pass
    cap_note = min(float(DODGE_CHANCE_CAP), base + sum(
        float(c.get("pct_add") or 0)
        for c in out[1:]
        if c.get("source", "").startswith(("passive:", "affix:", "gear:"))
        and "full_evade" not in str(c.get("source", ""))
    ))
    out.append(
        _contrib_row(
            source="cap:dodge_chance",
            label_ru=f"Эффективный потолок уклонения (бой): до {DODGE_CHANCE_CAP * 100:.0f}% (оценка {cap_note * 100:.1f}%)",
            pct_add=cap_note,
        )
    )
    return out
