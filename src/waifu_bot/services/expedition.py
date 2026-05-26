"""Expedition service: daily slots, start, chance/rewards, claim, cancel."""
from __future__ import annotations

import logging
import random
import secrets
from typing import Any
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from waifu_bot.db.models import ActiveExpedition, ExpeditionAffix, ExpeditionSlot, HiredWaifu, Player
from waifu_bot.services.hidden_skills import (
    get_hidden_skill_bonuses,
    increment_skill_counter,
    sync_loyal_commander_counter,
)
from waifu_bot.services.passive_skills import (
    expedition_reward_multiplier,
    expedition_success_probability_boost,
    get_passive_skill_bonuses,
)
from waifu_bot.game.expedition_data import AFFIX_BY_ID
from waifu_bot.game.expedition_perk_resolve import normalize_expedition_paired_perk_ids
from waifu_bot.game.expedition_difficulty_tags import (
    calc_tag_effectiveness_mult,
    sorted_tag_list,
    squad_covered_tags,
    tag_effectiveness_pct,
    union_affix_tags,
    union_legacy_affix_tags,
)
from waifu_bot.game.expedition_redesign import (
    PERK_CHALLENGE_CATEGORIES,
    affix_display_icon,
    events_count_for_duration,
    roman_numeral,
    union_challenge_categories_from_db_affix_rows,
)
from waifu_bot.game.constants import (
    EXPEDITION_AFFIX_PENALTY_PCT,
    EXPEDITION_BASE_EXP,
    EXPEDITION_BASE_GOLD,
    EXPEDITION_CANCEL_REWARD_PCT,
    EXPEDITION_CHANCE_CAP_MAX,
    EXPEDITION_CHANCE_CAP_MIN,
    EXPEDITION_DIFFICULTY_BASE_BONUS,
    EXPEDITION_DURATION_DECAY,
    EXPEDITION_EVENT_INTERVAL_MINUTES,
    EXPEDITION_FAILURE_REWARD_MULT,
    EXPEDITION_HP_DAMAGE_BASE,
    EXPEDITION_HP_MIN_PCT_TO_START,
    EXPEDITION_LEVEL_RATIO_MULT,
    EXPEDITION_MAX_CONCURRENT,
    EXPEDITION_MAX_SQUAD,
    EXPEDITION_MIN_SQUAD,
    EXPEDITION_OUTCOME_FAILURE,
    EXPEDITION_OUTCOME_PARTIAL,
    EXPEDITION_OUTCOME_SUCCESS,
    EXPEDITION_P_INDIVIDUAL_MAX,
    EXPEDITION_P_INDIVIDUAL_MIN,
    EXPEDITION_PERK_BONUS_BASE,
    EXPEDITION_PERK_LEVEL_MULT,
    EXPEDITION_SLOTS_PER_DAY,
    EXPEDITION_SUCCESS_REWARD_MULT,
    EXPEDITION_TIME_COEFFS,
    EXPEDITION_V13_DURATIONS,
    HIRED_EXP_LEVEL_BASE,
    HIRED_EXP_LEVEL_LINEAR,
    HIRED_EXP_LEVEL_SQUARE,
    HIRED_MAX_LEVEL,
)
from waifu_bot.game.expedition_narrative_catalog import (
    fallback_narrative_brief,
    pick_expedition_mode,
    pick_location_archetype,
    pick_narrative_style,
    resolve_archetype_and_mode,
    slot_preview_name,
)
from waifu_bot.services.expedition_ticks import run_one_tick

logger = logging.getLogger(__name__)

try:
    from zoneinfo import ZoneInfo
    MOSCOW_TZ = ZoneInfo("Europe/Moscow")
except Exception:
    MOSCOW_TZ = timezone.utc

# Базовые локации (ТЗ v1.1 / cursor_plan_6): (name, biome_tag, weight)
BASE_LOCATIONS = [
    ("Пещера", "cave", 100),
    ("Руины", "ruins", 100),
    ("Лес", "forest", 100),
    ("Болото", "swamp", 80),
    ("Крепость", "fortress", 80),
    ("Храм", "ruins", 80),
    ("Катакомбы", "crypt", 70),
    ("Шахта", "cave", 70),
    ("Пустыня", "desert", 60),
    ("Вулкан", "volcano", 50),
    ("Бездна", "abyss", 40),
    ("Воздушный замок", "sky", 40),
    ("Морское дно", "sea_depth", 40),
    ("Тундра", "tundra", 50),
]


def _moscow_today():
    return datetime.now(tz=MOSCOW_TZ).date()


async def _apply_narrative_at_start(
    active: ActiveExpedition,
    *,
    location_archetype_id: str | None,
    expedition_mode_id: str | None,
    legacy_base_location: str | None,
    affix_rows: list,
    squad: list[HiredWaifu],
    events_total: int,
    duration_minutes: int,
) -> str | None:
    """Генерирует narrative_brief при старте и обновляет display поля. Возвращает текст intro для Telegram."""
    from waifu_bot.services.expedition_events_ai import (
        format_expedition_start_intro_telegram,
        generate_expedition_narrative_brief,
    )

    style_rng = random.Random(int(active.id))
    narrative_style = pick_narrative_style(style_rng)
    arch, mode = resolve_archetype_and_mode(
        location_archetype_id=location_archetype_id,
        expedition_mode_id=expedition_mode_id,
        legacy_base_location=legacy_base_location,
        rng=style_rng,
    )
    affix_names = [str(getattr(a, "name", "") or "").strip() for a in affix_rows if getattr(a, "name", None)]
    affix_hints = [str(getattr(a, "description_hint", "") or "").strip() for a in affix_rows]
    squad_names = [w.name or "Наёмница" for w in squad]

    brief = await generate_expedition_narrative_brief(
        archetype_id=arch.id,
        archetype_name=arch.name_ru,
        archetype_hints=list(arch.narrative_hints),
        mode_id=mode.id,
        mode_name=mode.name_ru,
        mode_focus=mode.narrative_focus,
        mode_prompt_rules=mode.prompt_rules_ru,
        affix_names=affix_names,
        affix_hints=affix_hints,
        events_total=max(1, int(events_total or 1)),
        duration_minutes=int(duration_minutes),
        squad_names=squad_names,
        narrative_style=narrative_style,
    )
    if not brief:
        brief = fallback_narrative_brief(
            arch,
            mode,
            max(1, int(events_total or 1)),
            affix_names=affix_names,
            rng=style_rng,
            narrative_style=narrative_style,
            squad_names=squad_names,
        )

    brief.setdefault("narrative_style_id", narrative_style.id)
    brief.setdefault("narrative_style_name", narrative_style.name_ru)
    if not brief.get("intro_narrative"):
        brief["intro_narrative"] = brief.get("setting_summary") or ""

    active.location_archetype_id = arch.id
    active.expedition_mode_id = mode.id
    active.narrative_brief = brief
    active.display_base_location = (brief.get("title") or slot_preview_name(mode, arch)).strip()[:120]
    active.display_biome_tag = arch.biome_tag

    return format_expedition_start_intro_telegram(
        title=active.display_base_location or brief.get("title") or "Экспедиция",
        intro_narrative=str(brief.get("intro_narrative") or ""),
        mode_name=mode.name_ru,
        archetype_name=arch.name_ru,
        squad_names=squad_names,
        style_name=str(brief.get("narrative_style_name") or narrative_style.name_ru),
    )


def _build_expedition_name(base_location: str, affix_objects: list) -> str:
    """
    Детерминированная сборка названия: [PREFIX_1] [PREFIX_2] BASE [SUFFIX_1 и SUFFIX_2].
    0 аффиксов → только base_location (например «Руины»).
    """
    if not affix_objects:
        return base_location
    prefixes = [a for a in affix_objects if getattr(a, "type", None) == "prefix"]
    suffixes = [a for a in affix_objects if getattr(a, "type", None) == "suffix"]
    name_parts = [a.name for a in prefixes] + [base_location]
    if suffixes:
        name_parts.append(" и ".join(a.name for a in suffixes))
    return " ".join(name_parts)


def _squad_power(waifus: list[HiredWaifu]) -> float:
    """Мощь отряда: сумма по вайфу (уровень × множитель редкости)."""
    total = 0.0
    for w in waifus:
        lvl = max(1, int(w.level or 1))
        rarity_mult = 1.0 + 0.2 * (int(w.rarity or 1) - 1)  # 1->1, 2->1.2, 5->1.8
        total += lvl * rarity_mult
    return total


def _squad_perk_ids(waifus: list[HiredWaifu]) -> set[str]:
    """Собрать все id перков отряда (для проверки контраффиксов)."""
    out: set[str] = set()
    for w in waifus:
        for pid in w.perks or []:
            if isinstance(pid, str):
                out.add(pid)
            else:
                out.add(str(pid))
    return out


def _perk_matches_expedition_slot(
    pid: str,
    paired_perks: set[str],
    challenge_union: frozenset[str] | None,
) -> bool:
    """Точное совпадение с нормализованным списком или пересечение категорий испытаний с тиками v1.3."""
    if pid in paired_perks:
        return True
    if challenge_union:
        cats = PERK_CHALLENGE_CATEGORIES.get(pid)
        if cats and (cats & challenge_union):
            return True
    return False


def slot_challenge_categories_union(
    slot: ExpeditionSlot,
    affix_by_id: dict[int, Any] | None,
) -> frozenset[str]:
    """Объединение challenge-категорий по всем аффиксам слота."""
    aids = list(getattr(slot, "affix_ids", None) or [])
    if not aids or not affix_by_id:
        return frozenset()
    rows = [affix_by_id[int(aid)] for aid in aids if int(aid) in affix_by_id]
    return union_challenge_categories_from_db_affix_rows(rows) if rows else frozenset()


def slot_active_tags(
    slot: ExpeditionSlot,
    affix_by_id: dict[int, Any] | None,
) -> frozenset[str]:
    """Union игровых тегов сложности слота (кэш или вычисление)."""
    from waifu_bot.game.expedition_difficulty_tags import (
        DIFFICULTY_TAG_LABEL_RU,
        union_affix_tags,
        union_legacy_affix_tags,
    )

    cached = getattr(slot, "difficulty_tags", None)
    if cached:
        valid = {str(t) for t in cached if str(t) in DIFFICULTY_TAG_LABEL_RU}
        if valid:
            return frozenset(valid)
    aids = list(getattr(slot, "affix_ids", None) or [])
    if aids and affix_by_id:
        rows = [affix_by_id[int(aid)] for aid in aids if int(aid) in affix_by_id]
        if rows:
            return union_affix_tags(rows)
    legacy = list(getattr(slot, "affixes", None) or [])
    if legacy:
        return union_legacy_affix_tags(legacy)
    return frozenset()


def tags_snapshot_for_affix_rows(rows: list) -> list[str]:
    from waifu_bot.game.expedition_difficulty_tags import sorted_tag_list, union_affix_tags

    return sorted_tag_list(union_affix_tags(rows))


def tag_preview_for_squad(
    squad: list[HiredWaifu],
    slot: ExpeditionSlot,
    affix_by_id: dict[int, Any] | None,
    affix_level: int = 1,
) -> dict:
    from waifu_bot.game.expedition_difficulty_tags import (
        calc_tag_effectiveness_mult,
        squad_covered_tags,
        sorted_tag_list,
        squad_perk_effectiveness_pct,
        tag_effectiveness_pct,
    )

    active = slot_active_tags(slot, affix_by_id)
    covered = squad_covered_tags(squad) & active
    al = max(1, min(5, int(affix_level or 1)))
    mult = calc_tag_effectiveness_mult(active, covered, squad=squad, affix_level=al)
    return {
        "active_tags": sorted_tag_list(active),
        "covered_tags": sorted_tag_list(covered),
        "tag_effectiveness_mult": round(mult, 4),
        "tag_effectiveness_pct": tag_effectiveness_pct(
            active, covered, squad=squad, affix_level=al
        ),
        "perk_effectiveness_pct": squad_perk_effectiveness_pct(active, covered, squad, al),
        "affix_level": al,
    }


def _slot_required_perks(slot: ExpeditionSlot) -> set[str]:
    """Перки, полезные для этого слота (контраффиксы аффиксов слота)."""
    # Новая схема: слот хранит paired_perks из expedition_affixes (нормализуем черновые id)
    if getattr(slot, "paired_perks", None):
        return set(normalize_expedition_paired_perk_ids(slot.paired_perks))
    # Старая схема: affixes = список строковых id, контраффикс один на аффикс
    out: set[str] = set()
    for aid in slot.affixes or []:
        affix = AFFIX_BY_ID.get(aid if isinstance(aid, str) else str(aid))
        if affix and getattr(affix, "counter", None):
            out.add(str(affix.counter))
    return out


def _effective_affix_penalty(
    slot: ExpeditionSlot,
    squad_waifus: list[HiredWaifu],
) -> int:
    """
    Суммарный штраф за аффиксы слота; перки наёмных вайфу снимают штраф за контраффикс.
    Новая схема (affix_ids): урон учтён в damage_mult, штраф к шансу не начисляем.
    """
    if getattr(slot, "affix_ids", None):
        return 0
    affix_ids = slot.affixes or []
    perk_ids = _squad_perk_ids(squad_waifus)
    total = 0
    for aid in affix_ids:
        affix = AFFIX_BY_ID.get(aid if isinstance(aid, str) else str(aid))
        if not affix:
            total += EXPEDITION_AFFIX_PENALTY_PCT
            continue
        counter_perk_id = getattr(affix, "counter", None)
        if counter_perk_id and counter_perk_id in perk_ids:
            continue
        total += getattr(affix, "penalty", EXPEDITION_AFFIX_PENALTY_PCT) or EXPEDITION_AFFIX_PENALTY_PCT
    return total


def _effective_level_for_slot(slot_number: int, player_level: int, slot_difficulty: int | None = None) -> int:
    """Уровень слота для расчёта шанса. Если задан slot_difficulty (1+sum affix) — используем его."""
    if slot_difficulty is not None:
        return max(1, player_level - 5 + (slot_difficulty - 1) * 2)
    base = max(1, player_level - 3)
    return max(1, base + (slot_number - 1) * 3)


def _unit_perk_ids(waifu: HiredWaifu) -> list[tuple[str, int]]:
    """Список (perk_id, level) для вайфу. Уровень читается из perk_levels, по умолчанию 1."""
    perk_levels: dict = getattr(waifu, "perk_levels", None) or {}
    out: list[tuple[str, int]] = []
    for p in waifu.perks or []:
        pid = str(p) if p else ""
        if pid:
            out.append((pid, int(perk_levels.get(pid, 1))))
    return out


def get_duration_multipliers(duration_minutes: int) -> dict:
    """
    ТЗ v1.1: длительность влияет на урон, награду и число испытаний.
    ratio = duration / 60.
    """
    ratio = duration_minutes / 60.0
    return {
        "damage_mult": round(0.6 + ratio * 0.4, 2),
        "reward_mult": round(0.5 + ratio * 0.5, 2),
        "events_count": max(1, round(duration_minutes / 7.5)),
    }


def exp_to_next_level_hired(level: int) -> int:
    """Опыт до следующего уровня наёмницы: 50 + (level-1)*50 + (level-1)^2*5 (ТЗ v1.1)."""
    if level < 1:
        return HIRED_EXP_LEVEL_BASE
    n = level - 1
    return HIRED_EXP_LEVEL_BASE + n * HIRED_EXP_LEVEL_LINEAR + (n * n) * HIRED_EXP_LEVEL_SQUARE


def calculate_unit_chance(
    unit: HiredWaifu,
    slot_level: int,
    paired_perks: set[str],
    difficulty_tier: int = 1,
    *,
    challenge_union: frozenset[str] | None = None,
) -> tuple[float, float, float, list[str]]:
    """
    Индивидуальный шанс P_i наёмницы.
    P_i = clamp(P_level_i + P_perks_i, 0.05, 0.90).
    ТЗ v1.1: DIFFICULTY_BASE_BONUS для лёгкой/тяжёлой сложности.
    Возвращает (p_individual, p_level, p_perks, matched_perk_ids).
    """
    unit_level = max(1, int(unit.level or 1))
    level_ratio = unit_level / slot_level if slot_level else 0.0
    bonus = EXPEDITION_DIFFICULTY_BASE_BONUS.get(difficulty_tier, 0.0)
    p_level = min(0.65, level_ratio * EXPEDITION_LEVEL_RATIO_MULT + bonus)

    matched: list[str] = []
    perk_bonus = 0.0
    for pid, plevel in _unit_perk_ids(unit):
        if _perk_matches_expedition_slot(pid, paired_perks, challenge_union):
            matched.append(pid)
            perk_bonus += EXPEDITION_PERK_BONUS_BASE * (1.0 + (plevel - 1) * EXPEDITION_PERK_LEVEL_MULT)
    p_perks = min(0.30, perk_bonus)

    p_individual = max(
        EXPEDITION_P_INDIVIDUAL_MIN,
        min(EXPEDITION_P_INDIVIDUAL_MAX, round(p_level + p_perks, 4)),
    )
    return (p_individual, round(p_level, 4), round(p_perks, 4), matched)


def _slot_difficulty_tier(slot: ExpeditionSlot) -> int:
    """Сложность слота 1..5: из slot.difficulty (сумма аффиксов) или по номеру слота."""
    d = getattr(slot, "difficulty", None)
    if d is not None:
        if d <= 1:
            return 1
        if d <= 3:
            return 3
        return 5
    sn = int(slot.slot or 1)
    return {1: 1, 2: 3, 3: 5}.get(sn, 3)


def calculate_squad_chance(
    squad: list[HiredWaifu],
    slot: ExpeditionSlot,
    player_level: int,
    duration_minutes: int | None = None,
    *,
    challenge_union: frozenset[str] | None = None,
) -> dict:
    """
    Итоговый шанс отряда: 1 − ∏(1 − P_i).
    ТЗ v1.1: difficulty_tier для бонуса, опционально duration_minutes для decay по событиям.
    Возвращает chance, chance_pct, label, units, squad_size, [events_count, duration_damage_mult, duration_reward_mult].
    """
    if not squad:
        return {
            "chance": 0.0,
            "chance_pct": 0.0,
            "label": "Невозможно",
            "units": [],
            "squad_size": 0,
            "events_count": 1,
            "duration_damage_mult": 1.0,
            "duration_reward_mult": 1.0,
        }
    slot_difficulty = getattr(slot, "difficulty", None)
    slot_level = _effective_level_for_slot(
        int(slot.slot or 1), player_level,
        slot_difficulty=int(slot_difficulty) if slot_difficulty is not None else None,
    )
    paired_perks = _slot_required_perks(slot)
    difficulty_tier = _slot_difficulty_tier(slot)

    unit_chances: list[dict] = []
    for unit in squad:
        p_i, p_level, p_perks, matched = calculate_unit_chance(
            unit,
            slot_level,
            paired_perks,
            difficulty_tier=difficulty_tier,
            challenge_union=challenge_union,
        )
        unit_chances.append({
            "unit_id": unit.id,
            "name": unit.name or "Вайфу",
            "p_individual": round(p_i, 3),
            "p_level": round(p_level, 3),
            "p_perks": round(p_perks, 3),
            "matched_perks": matched,
        })

    p_fail_squad = 1.0
    for uc in unit_chances:
        p_fail_squad *= 1.0 - uc["p_individual"]
    p_single = 1.0 - p_fail_squad

    if duration_minutes is not None and duration_minutes > 0:
        mults = get_duration_multipliers(duration_minutes)
        events_count = mults["events_count"]
        decay = EXPEDITION_DURATION_DECAY
        p_total = p_single * max(0.3, 1.0 - decay * (events_count - 1))
        p_success_squad = round(max(0.05, min(0.95, p_total)), 3)
        out = {
            "chance": p_success_squad,
            "chance_pct": round(p_success_squad * 100, 1),
            "units": unit_chances,
            "squad_size": len(squad),
            "events_count": events_count,
            "duration_damage_mult": mults["damage_mult"],
            "duration_reward_mult": mults["reward_mult"],
        }
    else:
        p_success_squad = round(p_single, 3)
        out = {
            "chance": p_success_squad,
            "chance_pct": round(p_success_squad * 100, 1),
            "units": unit_chances,
            "squad_size": len(squad),
            "events_count": 1,
            "duration_damage_mult": 1.0,
            "duration_reward_mult": 1.0,
        }

    if out["chance"] >= 0.75:
        out["label"] = "Отличный"
    elif out["chance"] >= 0.50:
        out["label"] = "Высокий"
    elif out["chance"] >= 0.25:
        out["label"] = "Средний"
    else:
        out["label"] = "Низкий"
    return out


def enrich_chance_with_tags(
    data: dict,
    squad: list[HiredWaifu],
    slot: ExpeditionSlot,
    affix_by_id: dict[int, Any] | None,
    affix_level: int = 1,
) -> dict:
    """Добавляет поля тегов v1.4 к результату calculate_squad_chance."""
    tp = tag_preview_for_squad(squad, slot, affix_by_id, affix_level=affix_level)
    data.update(tp)
    return data


def calculate_success_chance(
    slot: ExpeditionSlot,
    squad_waifus: list[HiredWaifu],
    player_level: int,
    *,
    challenge_union: frozenset[str] | None = None,
) -> tuple[float, list[str]]:
    """
    Скалярный шанс успеха отряда (для обратной совместимости и для start/roll).
    Возвращает (chance 0.05–0.95, список id совпавших перков по отряду).
    """
    data = calculate_squad_chance(squad_waifus, slot, player_level, challenge_union=challenge_union)
    all_matched: list[str] = []
    for u in data.get("units", []):
        all_matched.extend(u.get("matched_perks", []))
    return (data["chance"], list(dict.fromkeys(all_matched)))


def _chance_and_rewards(
    slot: ExpeditionSlot,
    duration_minutes: int,
    squad_power: float,
    squad_waifus: list[HiredWaifu],
    player_level: int | None = None,
    *,
    challenge_union: frozenset[str] | None = None,
) -> tuple[float, int, int]:
    """
    Рассчитывает шанс успеха (с учётом длительности, ТЗ v1.1) и базовые награды (золото, опыт).
    Награды — база для исхода (success/partial/failure применяются при завершении).
    """
    mults = get_duration_multipliers(duration_minutes)
    reward_coeff = mults["reward_mult"]
    affix_penalty = _effective_affix_penalty(slot, squad_waifus)

    if player_level is not None:
        data = calculate_squad_chance(
            squad_waifus,
            slot,
            player_level,
            duration_minutes=duration_minutes,
            challenge_union=challenge_union,
        )
        chance_01 = data["chance"]
        chance = chance_01 * 100.0 - affix_penalty
        chance = max(EXPEDITION_CHANCE_CAP_MIN, min(EXPEDITION_CHANCE_CAP_MAX, chance))
    else:
        coeffs = EXPEDITION_TIME_COEFFS.get(duration_minutes, (1.0, 1.0))
        _diff_coeff, _ = coeffs
        base_diff = max(1, int(slot.base_difficulty or 100))
        effective_diff = base_diff * _diff_coeff
        base_chance = (squad_power / effective_diff) * 100.0 if effective_diff else 0.0
        chance = base_chance - affix_penalty
        chance = chance * (1.2 - 0.2 * _diff_coeff)
        chance = max(EXPEDITION_CHANCE_CAP_MIN, min(EXPEDITION_CHANCE_CAP_MAX, chance))

    base_gold = int(slot.base_gold or EXPEDITION_BASE_GOLD)
    base_exp = int(slot.base_experience or EXPEDITION_BASE_EXP)
    slot_reward_mult = getattr(slot, "reward_mult", None) or 1.0
    reward_gold = max(0, int(base_gold * reward_coeff * slot_reward_mult))
    reward_exp = max(0, int(base_exp * reward_coeff * slot_reward_mult))
    return round(chance, 2), reward_gold, reward_exp


async def _expedition_passive_p_success(
    session: AsyncSession, player_id: int, chance_pct: float | int | None
) -> float:
    """Шанс успеха при броске исхода: базовый шанс слота + бонус пассивного дерева."""
    p_base = float(chance_pct or 0) / 100.0
    ps = await get_passive_skill_bonuses(session, player_id)
    hs = await get_hidden_skill_bonuses(session, player_id)
    boost = expedition_success_probability_boost(ps, hs)
    return min(0.95, max(0.05, p_base + boost))


# Множители наград по исходу (ТЗ v1.1)
OUTCOME_REWARD_MULTIPLIERS = {
    EXPEDITION_OUTCOME_SUCCESS: {"gold": 1.0, "exp": 1.0, "item": True},
    EXPEDITION_OUTCOME_PARTIAL: {"gold": 0.7, "exp": 0.7, "item": False},
    EXPEDITION_OUTCOME_FAILURE: {"gold": 0.4, "exp": 0.5, "item": False},
}
OUTCOME_LABELS = {
    EXPEDITION_OUTCOME_SUCCESS: "✅ Успешно завершена",
    EXPEDITION_OUTCOME_PARTIAL: "⚠️ Завершена с потерями",
    EXPEDITION_OUTCOME_FAILURE: "❌ Провал",
}


def _outcome_from_squad_hp_ratio(squad: list) -> str:
    """Исход v1.3 по суммарному HP отряда после тиков (без ОВ)."""
    if not squad:
        return EXPEDITION_OUTCOME_FAILURE
    total_max = sum(max(1, int(getattr(w, "max_hp", 1) or 1)) for w in squad)
    total_cur = sum(max(0, int(getattr(w, "current_hp", 0) or 0)) for w in squad)
    r = total_cur / total_max if total_max else 0.0
    if r < 0.12:
        return EXPEDITION_OUTCOME_FAILURE
    if r >= 0.52:
        return EXPEDITION_OUTCOME_SUCCESS
    return EXPEDITION_OUTCOME_PARTIAL


def _roll_expedition_outcome(p_success: float) -> str:
    """Случайный исход по P_success (ТЗ v1.1): success / partial_success / failure."""
    r = random.random()
    if r < p_success:
        return EXPEDITION_OUTCOME_SUCCESS
    if r < p_success + 0.3:
        return EXPEDITION_OUTCOME_PARTIAL
    return EXPEDITION_OUTCOME_FAILURE


def _apply_exp_to_hired_unit(unit: HiredWaifu, exp: int) -> tuple[bool, int]:
    """
    Начислить опыт наёмнице; лвлап с +1 perk_upgrade_points (ТЗ v1.1).
    При лвлапе пересчитываем max_hp и ограничиваем current_hp новым максимумом.
    Возвращает (leveled_up: bool, new_level: int).
    """
    exp_current = getattr(unit, "exp_current", 0) or 0
    level = max(1, int(unit.level or 1))
    unit.exp_current = exp_current + exp
    leveled_up = False
    while level < HIRED_MAX_LEVEL and unit.exp_current >= exp_to_next_level_hired(level):
        unit.exp_current -= exp_to_next_level_hired(level)
        level += 1
        unit.level = level
        leveled_up = True
        unit.perk_upgrade_points = (getattr(unit, "perk_upgrade_points", 0) or 0) + 1
    if level >= HIRED_MAX_LEVEL and unit.exp_current > exp_to_next_level_hired(HIRED_MAX_LEVEL):
        unit.exp_current = exp_to_next_level_hired(HIRED_MAX_LEVEL)
    unit.level = level
    if leveled_up:
        new_max_hp = 50 + level * 15
        unit.max_hp = new_max_hp
        unit.current_hp = min(getattr(unit, "current_hp", new_max_hp), new_max_hp)
    return (leveled_up, level)


class ExpeditionService:
    """Сервис экспедиций: слоты, старт, завершение, награды."""

    async def get_slots(self, session: AsyncSession) -> list[ExpeditionSlot]:
        """Слоты экспедиций на сегодня (3 шт.), при необходимости создаёт."""
        today = _moscow_today()
        return await self._ensure_day_slots(session, today)

    async def get_used_slot_ids(self, session: AsyncSession, player_id: int) -> set[int]:
        """ID слотов, по которым у игрока уже есть экспедиция (активная или завершённая) — слот «использован»."""
        stmt = select(ActiveExpedition.expedition_slot_id).where(
            ActiveExpedition.player_id == player_id
        )
        scalars = (await session.execute(stmt)).scalars()
        return {x for x in scalars.all() if x is not None}

    async def get_active(
        self, session: AsyncSession, player_id: int
    ) -> list[ActiveExpedition]:
        """Активные экспедиции игрока (не отменённые, не забранные)."""
        stmt = (
            select(ActiveExpedition)
            .where(
                and_(
                    ActiveExpedition.player_id == player_id,
                    ActiveExpedition.cancelled.is_(False),
                    ActiveExpedition.claimed.is_(False),
                )
            )
            .order_by(ActiveExpedition.ends_at)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def _count_active_expeditions(self, session: AsyncSession, player_id: int) -> int:
        stmt = select(func.count()).select_from(ActiveExpedition).where(
            ActiveExpedition.player_id == player_id,
            ActiveExpedition.cancelled.is_(False),
            ActiveExpedition.claimed.is_(False),
        )
        return int((await session.execute(stmt)).scalar_one() or 0)

    async def _lock_squad_expedition(self, session: AsyncSession, active_id: int, squad_ids: list[int]) -> None:
        for wid in squad_ids:
            w = await session.get(HiredWaifu, wid)
            if w:
                w.expedition_id = active_id

    async def _unlock_squad_expedition(self, session: AsyncSession, squad_ids: list[int]) -> None:
        for wid in squad_ids:
            w = await session.get(HiredWaifu, wid)
            if w:
                w.expedition_id = None

    async def process_due_ticks(
        self, session: AsyncSession
    ) -> list[tuple[int, str | None, str | None]]:
        """Тики 15 мин: (player_id, telegram_narrative, telegram_status) для двух DM в ЛС."""
        now = datetime.now(tz=timezone.utc)
        stmt = select(ActiveExpedition).where(
            ActiveExpedition.cancelled.is_(False),
            ActiveExpedition.claimed.is_(False),
            ActiveExpedition.next_tick_at.isnot(None),
            ActiveExpedition.next_tick_at <= now,
        )
        actives = list((await session.execute(stmt)).scalars().all())
        out: list[tuple[int, str | None, str | None]] = []
        for active in actives:
            if int(active.events_done or 0) >= int(active.events_total or 0):
                active.next_tick_at = None
                continue
            res = await run_one_tick(session, active, silent=False)
            if not res.get("ok"):
                continue
            narr = (res.get("telegram_narrative") or "").strip()
            stat = (res.get("telegram_status") or "").strip()
            if narr or stat:
                out.append((int(active.player_id), narr or None, stat or None))
        if actives:
            await session.commit()
        return out

    async def start(
        self,
        session: AsyncSession,
        player_id: int,
        expedition_slot_id: int | None,
        squad_waifu_ids: list[int],
        duration_minutes: int,
        *,
        affix_template_id: int | None = None,
        affix_level: int | None = None,
        display_base_location: str | None = None,
        display_biome_tag: str | None = None,
        difficulty_level: int | None = None,
    ) -> dict:
        """
        Запуск экспедиции: v1.3 — тип аффикса × уровень × длительность; либо старый дневной слот.
        Ежедневный слот + difficulty_level + длительность из EXPEDITION_V13_DURATIONS → тики v1.3 с привязкой к слоту.
        """
        if affix_template_id is not None and affix_level is not None and display_base_location:
            return await self._start_v13(
                session,
                player_id,
                squad_waifu_ids,
                duration_minutes,
                affix_template_id=int(affix_template_id),
                affix_level=int(affix_level),
                display_base_location=display_base_location,
                display_biome_tag=display_biome_tag,
            )

        if (
            expedition_slot_id is not None
            and difficulty_level is not None
            and duration_minutes in EXPEDITION_V13_DURATIONS
        ):
            return await self._start_daily_slot_v13(
                session,
                player_id,
                int(expedition_slot_id),
                squad_waifu_ids,
                duration_minutes,
                int(difficulty_level),
            )

        if expedition_slot_id is None:
            return {"error": "missing_expedition_config"}

        if duration_minutes not in EXPEDITION_TIME_COEFFS:
            return {"error": "invalid_duration"}
        if not (EXPEDITION_MIN_SQUAD <= len(squad_waifu_ids) <= EXPEDITION_MAX_SQUAD):
            return {"error": "squad_size", "min": EXPEDITION_MIN_SQUAD, "max": EXPEDITION_MAX_SQUAD}

        slot = await session.get(ExpeditionSlot, expedition_slot_id)
        if not slot:
            return {"error": "slot_not_found"}

        today = _moscow_today()
        if slot.day != today:
            return {"error": "slot_expired"}

        squad: list[HiredWaifu] = []
        for wid in squad_waifu_ids:
            w = await session.get(HiredWaifu, wid)
            if not w or w.player_id != player_id:
                return {"error": "waifu_not_found", "waifu_id": wid}
            if not (w.squad_position and 1 <= w.squad_position <= 6):
                return {"error": "waifu_not_in_squad", "waifu_id": wid}
            squad.append(w)

        used_ids = await self.get_used_slot_ids(session, player_id)
        if expedition_slot_id in used_ids:
            return {"error": "already_started"}

        power = _squad_power(squad)
        player = await session.get(Player, player_id, options=[selectinload(Player.main_waifu)])
        player_level = (
            int(player.main_waifu.level or 1) if (player and player.main_waifu) else 1
        )
        affix_by_id: dict[int, Any] = {}
        if getattr(slot, "affix_ids", None):
            stmt_aff = select(ExpeditionAffix).where(ExpeditionAffix.id.in_(list(slot.affix_ids)))
            affix_rows = list((await session.execute(stmt_aff)).scalars().all())
            affix_by_id = {a.id: a for a in affix_rows}
        ch_union = slot_challenge_categories_union(slot, affix_by_id)
        chance_pct, reward_gold, reward_exp = _chance_and_rewards(
            slot,
            duration_minutes,
            power,
            squad,
            player_level=player_level,
            challenge_union=ch_union,
        )
        ps_exp = await get_passive_skill_bonuses(session, player_id)
        hs_exp = await get_hidden_skill_bonuses(session, player_id)
        rm = expedition_reward_multiplier(ps_exp, hs_exp)
        reward_gold = max(0, int(round(reward_gold * rm)))
        reward_exp = max(0, int(round(reward_exp * rm)))
        now = datetime.now(tz=timezone.utc)
        ends_at = now + timedelta(minutes=duration_minutes)

        active = ActiveExpedition(
            player_id=player_id,
            expedition_slot_id=expedition_slot_id,
            started_at=now,
            ends_at=ends_at,
            duration_minutes=duration_minutes,
            chance=chance_pct,
            success=False,
            reward_gold=reward_gold,
            reward_experience=reward_exp,
            squad_waifu_ids=squad_waifu_ids,
        )
        session.add(active)
        await session.commit()
        await session.refresh(active)
        return {
            "success": True,
            "active_id": active.id,
            "expedition_name": slot.name,
            "chance": chance_pct,
            "success": False,
            "reward_gold": reward_gold,
            "reward_experience": reward_exp,
            "ends_at": ends_at.isoformat(),
            "duration_minutes": duration_minutes,
        }

    async def _start_v13(
        self,
        session: AsyncSession,
        player_id: int,
        squad_waifu_ids: list[int],
        duration_minutes: int,
        *,
        affix_template_id: int,
        affix_level: int,
        display_base_location: str,
        display_biome_tag: str | None,
    ) -> dict:
        """Экспедиция v1.3: без ОВ, тики каждые 15 мин."""
        if duration_minutes not in EXPEDITION_V13_DURATIONS:
            return {"error": "invalid_duration"}
        if not (1 <= affix_level <= 5):
            return {"error": "bad_affix_level"}
        loc = (display_base_location or "").strip()
        if not loc:
            return {"error": "missing_location"}
        if not (EXPEDITION_MIN_SQUAD <= len(squad_waifu_ids) <= EXPEDITION_MAX_SQUAD):
            return {"error": "squad_size", "min": EXPEDITION_MIN_SQUAD, "max": EXPEDITION_MAX_SQUAD}

        if await self._count_active_expeditions(session, player_id) >= EXPEDITION_MAX_CONCURRENT:
            return {"error": "too_many_expeditions", "max": EXPEDITION_MAX_CONCURRENT}

        affix_row = await session.get(ExpeditionAffix, affix_template_id)
        if not affix_row:
            return {"error": "affix_not_found"}

        squad: list[HiredWaifu] = []
        for wid in squad_waifu_ids:
            w = await session.get(HiredWaifu, wid)
            if not w or w.player_id != player_id:
                return {"error": "waifu_not_found", "waifu_id": wid}
            if w.expedition_id is not None:
                return {"error": "waifu_busy", "waifu_id": wid}
            max_hp = max(1, int(w.max_hp or 1))
            cur = int(getattr(w, "current_hp", max_hp) or 0)
            if cur / max_hp < EXPEDITION_HP_MIN_PCT_TO_START:
                return {"error": "waifu_low_hp", "waifu_id": wid}
            squad.append(w)

        events_total = events_count_for_duration(duration_minutes)
        ratio = duration_minutes / 60.0
        reward_mult = 0.5 + ratio * 0.5
        ar = float(affix_row.reward_mult or 1.0)
        level_bonus = 1.0 + (affix_level - 1) * 0.06
        reward_gold = int(EXPEDITION_BASE_GOLD * reward_mult * ar * level_bonus)
        reward_exp = int(EXPEDITION_BASE_EXP * reward_mult * ar * level_bonus)
        ps_exp = await get_passive_skill_bonuses(session, player_id)
        hs_exp = await get_hidden_skill_bonuses(session, player_id)
        rm = expedition_reward_multiplier(ps_exp, hs_exp)
        reward_gold = max(0, int(round(reward_gold * rm)))
        reward_exp = max(0, int(round(reward_exp * rm)))

        now = datetime.now(tz=timezone.utc)
        ends_at = now + timedelta(minutes=duration_minutes)

        from waifu_bot.game.expedition_difficulty_tags import sorted_tag_list, tags_for_db_affix_row

        tag_snap = sorted_tag_list(tags_for_db_affix_row(affix_row))

        active = ActiveExpedition(
            player_id=player_id,
            expedition_slot_id=None,
            started_at=now,
            ends_at=ends_at,
            duration_minutes=duration_minutes,
            chance=0.0,
            success=False,
            reward_gold=reward_gold,
            reward_experience=reward_exp,
            squad_waifu_ids=squad_waifu_ids,
            affix_level=affix_level,
            affix_template_id=affix_template_id,
            display_base_location=loc,
            display_biome_tag=(display_biome_tag or "").strip() or None,
            events_total=events_total,
            events_done=0,
            next_tick_at=now + timedelta(minutes=15),
            tick_state={},
            difficulty_tags_snapshot=tag_snap,
        )
        session.add(active)
        await session.flush()
        start_intro_narrative: str | None = None
        if events_total > 0:
            start_intro_narrative = await _apply_narrative_at_start(
                active,
                location_archetype_id=None,
                expedition_mode_id=None,
                legacy_base_location=loc,
                affix_rows=[affix_row],
                squad=squad,
                events_total=events_total,
                duration_minutes=duration_minutes,
            )
        await self._lock_squad_expedition(session, active.id, squad_waifu_ids)
        await session.commit()
        await session.refresh(active)
        exp_name = (active.display_base_location or loc).strip()
        return {
            "success": True,
            "active_id": active.id,
            "expedition_name": exp_name,
            "chance": 0.0,
            "success": False,
            "reward_gold": reward_gold,
            "reward_experience": reward_exp,
            "ends_at": ends_at.isoformat(),
            "duration_minutes": duration_minutes,
            "affix_icon": affix_display_icon(affix_row),
            "affix_level_roman": roman_numeral(affix_level),
            "events_total": events_total,
            "start_intro_narrative": start_intro_narrative,
        }

    async def _start_daily_slot_v13(
        self,
        session: AsyncSession,
        player_id: int,
        expedition_slot_id: int,
        squad_waifu_ids: list[int],
        duration_minutes: int,
        difficulty_level: int,
    ) -> dict:
        """Ежедневный слот: аффиксы из карточки, сложность I–V и длительность v13 — тики 15 мин, без требования позиций в таверне."""
        if duration_minutes not in EXPEDITION_V13_DURATIONS:
            return {"error": "invalid_duration"}
        if not (1 <= difficulty_level <= 5):
            return {"error": "bad_affix_level"}
        if not (EXPEDITION_MIN_SQUAD <= len(squad_waifu_ids) <= EXPEDITION_MAX_SQUAD):
            return {"error": "squad_size", "min": EXPEDITION_MIN_SQUAD, "max": EXPEDITION_MAX_SQUAD}

        if await self._count_active_expeditions(session, player_id) >= EXPEDITION_MAX_CONCURRENT:
            return {"error": "too_many_expeditions", "max": EXPEDITION_MAX_CONCURRENT}

        slot = await session.get(ExpeditionSlot, expedition_slot_id)
        if not slot:
            return {"error": "slot_not_found"}
        today = _moscow_today()
        if slot.day != today:
            return {"error": "slot_expired"}

        used_ids = await self.get_used_slot_ids(session, player_id)
        if expedition_slot_id in used_ids:
            return {"error": "already_started"}

        affix_ids = list(getattr(slot, "affix_ids", None) or [])
        affix_row = None
        if affix_ids:
            stmt = select(ExpeditionAffix).where(ExpeditionAffix.id.in_(affix_ids))
            affix_rows = list((await session.execute(stmt)).scalars().all())
            affix_by_id = {a.id: a for a in affix_rows}
            rows = [affix_by_id[i] for i in affix_ids if i in affix_by_id]
            if rows:
                affix_row = next((r for r in rows if (r.category or "").lower() == "enemy"), rows[0])

        loc = (slot.base_location or "").strip() or (slot.computed_name or slot.name or "Экспедиция").strip()
        biome = (slot.biome_tag or "").strip() or None

        squad: list[HiredWaifu] = []
        for wid in squad_waifu_ids:
            w = await session.get(HiredWaifu, wid)
            if not w or w.player_id != player_id:
                return {"error": "waifu_not_found", "waifu_id": wid}
            if w.expedition_id is not None:
                return {"error": "waifu_busy", "waifu_id": wid}
            max_hp = max(1, int(w.max_hp or 1))
            cur = int(getattr(w, "current_hp", max_hp) or 0)
            if cur / max_hp < EXPEDITION_HP_MIN_PCT_TO_START:
                return {"error": "waifu_low_hp", "waifu_id": wid}
            squad.append(w)

        has_affix = affix_row is not None
        events_total = events_count_for_duration(duration_minutes) if has_affix else 0
        ratio = duration_minutes / 60.0
        reward_mult = 0.5 + ratio * 0.5
        ar = float(affix_row.reward_mult or 1.0) if has_affix else 1.0
        level_bonus = 1.0 + (difficulty_level - 1) * 0.06
        slot_rm = float(slot.reward_mult or 1.0)
        base_g = max(1, int(slot.base_gold or EXPEDITION_BASE_GOLD))
        base_e = max(1, int(slot.base_experience or EXPEDITION_BASE_EXP))
        reward_gold = int(base_g * reward_mult * ar * level_bonus * slot_rm)
        reward_exp = int(base_e * reward_mult * ar * level_bonus * slot_rm)
        ps_exp = await get_passive_skill_bonuses(session, player_id)
        hs_exp = await get_hidden_skill_bonuses(session, player_id)
        rm = expedition_reward_multiplier(ps_exp, hs_exp)
        reward_gold = max(0, int(round(reward_gold * rm)))
        reward_exp = max(0, int(round(reward_exp * rm)))

        now = datetime.now(tz=timezone.utc)
        ends_at = now + timedelta(minutes=duration_minutes)

        affix_rows_for_tags = []
        if affix_ids:
            stmt_t = select(ExpeditionAffix).where(ExpeditionAffix.id.in_(affix_ids))
            affix_rows_for_tags = list((await session.execute(stmt_t)).scalars().all())
        tag_snap = tags_snapshot_for_affix_rows(affix_rows_for_tags) if affix_rows_for_tags else []

        active = ActiveExpedition(
            player_id=player_id,
            expedition_slot_id=expedition_slot_id,
            started_at=now,
            ends_at=ends_at,
            duration_minutes=duration_minutes,
            chance=0.0,
            success=False,
            reward_gold=reward_gold,
            reward_experience=reward_exp,
            squad_waifu_ids=squad_waifu_ids,
            affix_level=difficulty_level,
            affix_template_id=int(affix_row.id) if has_affix else None,
            display_base_location=loc,
            display_biome_tag=biome,
            events_total=events_total,
            events_done=0,
            next_tick_at=now + timedelta(minutes=15) if has_affix else None,
            tick_state={},
            difficulty_tags_snapshot=tag_snap,
        )
        session.add(active)
        await session.flush()
        start_intro_narrative: str | None = None
        if has_affix and events_total > 0:
            start_intro_narrative = await _apply_narrative_at_start(
                active,
                location_archetype_id=getattr(slot, "location_archetype_id", None),
                expedition_mode_id=getattr(slot, "expedition_mode_id", None),
                legacy_base_location=slot.base_location or loc,
                affix_rows=affix_rows_for_tags,
                squad=squad,
                events_total=events_total,
                duration_minutes=duration_minutes,
            )
        await self._lock_squad_expedition(session, active.id, squad_waifu_ids)
        await session.commit()
        await session.refresh(active)
        exp_name = (active.display_base_location or loc).strip()
        return {
            "success": True,
            "active_id": active.id,
            "expedition_name": exp_name,
            "chance": 0.0,
            "success": False,
            "reward_gold": reward_gold,
            "reward_experience": reward_exp,
            "ends_at": ends_at.isoformat(),
            "duration_minutes": duration_minutes,
            "affix_icon": affix_display_icon(affix_row) if affix_row else "",
            "affix_level_roman": roman_numeral(difficulty_level),
            "events_total": events_total,
            "start_intro_narrative": start_intro_narrative,
        }

    async def claim(
        self, session: AsyncSession, player_id: int, active_id: int
    ) -> dict:
        """Забрать награду по завершённой экспедиции. ТЗ v1.1: исход при первом claim, опыт только наёмницам."""
        active = await session.get(
            ActiveExpedition, active_id, options=[selectinload(ActiveExpedition.expedition_slot)]
        )
        if not active or active.player_id != player_id:
            return {"error": "not_found"}
        if active.claimed:
            return {"error": "already_claimed"}
        if active.cancelled:
            return {"error": "cancelled"}

        now = datetime.now(tz=timezone.utc)
        if now < active.ends_at:
            return {"error": "not_finished", "ends_at": active.ends_at.isoformat()}

        player = await session.get(Player, player_id)
        if not player:
            return {"error": "player_not_found"}

        squad_ids = list(active.squad_waifu_ids or [])
        # v1.3: догоняем пропущенные тики (без ИИ)
        if int(active.events_total or 0) > 0:
            while int(active.events_done or 0) < int(active.events_total or 0):
                tick_res = await run_one_tick(session, active, silent=True)
                if not tick_res.get("ok"):
                    logger.warning("claim tick failed exp=%s: %s", active.id, tick_res)
                    break
            await session.flush()

        # Исход: v1.3 — по HP отряда; старые слоты — бросок по шансу
        if getattr(active, "outcome", None) is None:
            if int(active.events_total or 0) > 0:
                squad_rows: list = []
                for wid in squad_ids:
                    w = await session.get(HiredWaifu, wid)
                    if w and w.player_id == player_id:
                        squad_rows.append(w)
                outcome = _outcome_from_squad_hp_ratio(squad_rows)
                active.outcome = outcome
                mult = OUTCOME_REWARD_MULTIPLIERS[outcome]
                active.reward_gold = max(0, round(active.reward_gold * mult["gold"]))
                active.reward_experience = max(0, round(active.reward_experience * mult["exp"]))
                active.success = outcome == EXPEDITION_OUTCOME_SUCCESS
            else:
                p_success = await _expedition_passive_p_success(session, player_id, active.chance)
                outcome = _roll_expedition_outcome(p_success)
                active.outcome = outcome
                mult = OUTCOME_REWARD_MULTIPLIERS[outcome]
                active.reward_gold = max(0, round(active.reward_gold * mult["gold"]))
                active.reward_experience = max(0, round(active.reward_experience * mult["exp"]))
                active.success = outcome == EXPEDITION_OUTCOME_SUCCESS
        gold = active.reward_gold
        exp = active.reward_experience
        outcome = getattr(active, "outcome", None) or EXPEDITION_OUTCOME_FAILURE

        player.gold += gold
        active.claimed = True
        active.finished_at = now

        # Урон по старым слотам (v1.3 урон уже на тиках)
        if int(active.events_total or 0) <= 0:
            slot = active.expedition_slot
            num_events = max(1, active.duration_minutes // EXPEDITION_EVENT_INTERVAL_MINUTES)
            damage_mult = (slot.damage_mult if slot and slot.damage_mult is not None else 1.0) or 1.0
            base_diff = (slot.base_difficulty if slot else 100) or 100
            damage_per_event = max(0, int(EXPEDITION_HP_DAMAGE_BASE * damage_mult * (base_diff / 100.0)))
            total_damage = damage_per_event * num_events
            for wid in squad_ids:
                w = await session.get(HiredWaifu, wid)
                if w and w.player_id == player_id and total_damage > 0:
                    w.current_hp = max(0, getattr(w, "current_hp", w.max_hp) - total_damage)
                    w.hp_updated_at = now

        await self._unlock_squad_expedition(session, squad_ids)

        # Опыт только наёмницам отряда, поровну (ТЗ v1.1); ОВ не получает
        leveled_up_ids: list[int] = []
        if exp and squad_ids:
            per_waifu = max(0, exp // len(squad_ids))
            for wid in squad_ids:
                w = await session.get(HiredWaifu, wid)
                if w and w.player_id == player_id:
                    leveled, _ = _apply_exp_to_hired_unit(w, per_waifu)
                    if leveled:
                        leveled_up_ids.append(w.id)

        slot = active.expedition_slot
        expedition_name = (
            (active.display_base_location or "").strip()
            or (slot.name if slot else None)
            or "Экспедиция"
        )
        squad_names: list[str] = []
        for wid in squad_ids:
            w = await session.get(HiredWaifu, wid)
            if w and w.player_id == player_id:
                squad_names.append(w.name or "Вайфу")
        from waifu_bot.services.expedition_events_ai import generate_expedition_event
        import asyncio
        from waifu_bot.game.expedition_narrative_catalog import archetype_for_id, mode_for_id

        brief = getattr(active, "narrative_brief", None) or {}
        arch = archetype_for_id(getattr(active, "location_archetype_id", None))
        mode = mode_for_id(getattr(active, "expedition_mode_id", None))
        tick_summaries: list[str] = []
        ts = active.tick_state or {}
        if ts.get("last_narrative"):
            tick_summaries.append(str(ts["last_narrative"]))
        squad_prepared = ts.get("squad_prepared")
        try:
            # 2× OpenRouter (генерация + refine): 30s + 25s httpx внутри generate_expedition_event.
            event_text = await asyncio.wait_for(
                generate_expedition_event(
                    expedition_name=expedition_name,
                    success=outcome == EXPEDITION_OUTCOME_SUCCESS,
                    duration_minutes=active.duration_minutes,
                    squad_names=squad_names,
                    reward_gold=gold,
                    reward_experience=exp,
                    narrative_brief=brief if isinstance(brief, dict) else None,
                    mode_name=mode.name_ru if mode else None,
                    archetype_name=arch.name_ru if arch else None,
                    tick_summaries=tick_summaries,
                    squad_prepared=squad_prepared if isinstance(squad_prepared, bool) else None,
                ),
                timeout=65.0,
            )
        except asyncio.TimeoutError:
            event_text = f"Отряд вернулся из экспедиции «{expedition_name}». Награда: {gold} золота, {exp} опыта наёмницам."
        if event_text:
            active.event_text = event_text

        await increment_skill_counter(session, player_id, "expedition_complete", 1)
        for wid in squad_ids:
            hw = await session.get(HiredWaifu, wid)
            if hw and hw.player_id == player_id:
                hw.expedition_completions = int(hw.expedition_completions or 0) + 1
        await sync_loyal_commander_counter(session, player_id)

        if outcome == EXPEDITION_OUTCOME_SUCCESS:
            try:
                from waifu_bot.services.guild_progress import apply_expedition_success_guild

                await apply_expedition_success_guild(session, player_id)
            except Exception:
                pass

        await session.commit()
        return {
            "success": True,
            "active_id": active_id,
            "success_result": outcome == EXPEDITION_OUTCOME_SUCCESS,
            "outcome": outcome,
            "gold_gained": gold,
            "experience_gained": exp,
            "gold_total": player.gold,
            "event_text": getattr(active, "event_text", None) or event_text,
            "leveled_up_ids": leveled_up_ids,
        }

    async def abort_early(
        self, session: AsyncSession, player_id: int, active_id: int
    ) -> dict:
        """Досрочное завершение по кнопке в Telegram: доля награды как при отмене (EXPEDITION_CANCEL_REWARD_PCT)."""
        active = await session.get(
            ActiveExpedition, active_id, options=[selectinload(ActiveExpedition.expedition_slot)]
        )
        if not active or active.player_id != player_id:
            return {"error": "not_found"}
        if active.claimed:
            return {"error": "already_claimed"}

        player = await session.get(Player, player_id)
        if not player:
            return {"error": "player_not_found"}

        now = datetime.now(tz=timezone.utc)
        pct = EXPEDITION_CANCEL_REWARD_PCT / 100.0
        gold = max(0, int(active.reward_gold * pct))
        exp = max(0, int(active.reward_experience * pct))
        player.gold += gold
        active.claimed = True
        active.finished_at = now
        active.notification_sent = True

        squad_ids = active.squad_waifu_ids or []
        if exp and squad_ids:
            per_waifu = max(0, exp // len(squad_ids))
            for wid in squad_ids:
                w = await session.get(HiredWaifu, wid)
                if w and w.player_id == player_id:
                    w.experience = (w.experience or 0) + per_waifu

        await self._unlock_squad_expedition(session, list(squad_ids))

        slot = active.expedition_slot
        expedition_name = (
            (active.display_base_location or "").strip()
            or (slot.name if slot else None)
            or "Экспедиция"
        )
        squad_names: list[str] = []
        for wid in squad_ids:
            w = await session.get(HiredWaifu, wid)
            if w and w.player_id == player_id:
                squad_names.append(w.name or "Вайфу")
        from waifu_bot.services.expedition_events_ai import generate_expedition_event
        from waifu_bot.game.expedition_narrative_catalog import archetype_for_id, mode_for_id

        brief = getattr(active, "narrative_brief", None) or {}
        arch = archetype_for_id(getattr(active, "location_archetype_id", None))
        mode = mode_for_id(getattr(active, "expedition_mode_id", None))
        ts = active.tick_state or {}
        squad_prepared = ts.get("squad_prepared")
        event_text = await generate_expedition_event(
            expedition_name=expedition_name,
            success=active.success,
            duration_minutes=active.duration_minutes,
            squad_names=squad_names,
            reward_gold=gold,
            reward_experience=exp,
            narrative_brief=brief if isinstance(brief, dict) else None,
            mode_name=mode.name_ru if mode else None,
            archetype_name=arch.name_ru if arch else None,
            squad_prepared=squad_prepared if isinstance(squad_prepared, bool) else None,
        )
        if event_text:
            active.event_text = event_text

        await increment_skill_counter(session, player_id, "expedition_complete", 1)
        for wid in squad_ids:
            hw = await session.get(HiredWaifu, wid)
            if hw and hw.player_id == player_id:
                hw.expedition_completions = int(hw.expedition_completions or 0) + 1
        await sync_loyal_commander_counter(session, player_id)

        await session.commit()
        return {
            "success": True,
            "active_id": active_id,
            "gold_gained": gold,
            "experience_gained": exp,
            "gold_total": player.gold,
            "event_text": getattr(active, "event_text", None) or event_text,
        }

    async def cancel(
        self, session: AsyncSession, player_id: int, active_id: int
    ) -> dict:
        """Отменить экспедицию (из WebApp) и получить 50% награды."""
        active = await session.get(ActiveExpedition, active_id)
        if not active or active.player_id != player_id:
            return {"error": "not_found"}
        if active.claimed:
            return {"error": "already_claimed"}
        if active.cancelled:
            return {"error": "already_cancelled"}

        player = await session.get(Player, player_id)
        if not player:
            return {"error": "player_not_found"}

        pct = EXPEDITION_CANCEL_REWARD_PCT / 100.0
        gold = max(0, int(active.reward_gold * pct))
        exp = max(0, int(active.reward_experience * pct))
        player.gold += gold
        active.cancelled = True
        active.finished_at = datetime.now(tz=timezone.utc)
        active.claimed = True  # чтобы не забирать повторно

        await self._unlock_squad_expedition(session, list(active.squad_waifu_ids or []))

        await session.commit()
        return {
            "success": True,
            "active_id": active_id,
            "gold_gained": gold,
            "experience_gained": exp,
            "gold_total": player.gold,
        }

    async def get_finished_unnotified(
        self, session: AsyncSession
    ) -> list[ActiveExpedition]:
        """Экспедиции, у которых истёк срок и ещё не отправлено уведомление в ЛС.

        v1.3: не возвращаем запись, пока не обработаны все тики (иначе финальное ЛС
        уходит раньше последнего ИИ-сообщения).
        """
        now = datetime.now(tz=timezone.utc)
        et = func.coalesce(ActiveExpedition.events_total, 0)
        ed = func.coalesce(ActiveExpedition.events_done, 0)
        v13_ticks_complete = and_(ed >= et, ActiveExpedition.next_tick_at.is_(None))
        stmt = (
            select(ActiveExpedition)
            .where(
                and_(
                    ActiveExpedition.ends_at <= now,
                    ActiveExpedition.claimed.is_(False),
                    ActiveExpedition.cancelled.is_(False),
                    ActiveExpedition.notification_sent.is_(False),
                    or_(et == 0, v13_ticks_complete),
                )
            )
            .options(selectinload(ActiveExpedition.expedition_slot))
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def mark_notification_sent(
        self, session: AsyncSession, active_id: int
    ) -> None:
        """Пометить, что уведомление по экспедиции отправлено."""
        active = await session.get(ActiveExpedition, active_id)
        if active:
            active.notification_sent = True

    async def take_for_notification(
        self, session: AsyncSession, active_id: int
    ) -> bool:
        """ТЗ v1.1: атомарно «взять» экспедицию на отправку уведомления (только один воркер получит)."""
        from sqlalchemy import update
        stmt = (
            update(ActiveExpedition)
            .where(
                and_(
                    ActiveExpedition.id == active_id,
                    ActiveExpedition.notification_sent.is_(False),
                )
            )
            .values(notification_sent=True)
        )
        result = await session.execute(stmt)
        return result.rowcount > 0

    async def ensure_outcome_and_rewards(
        self, session: AsyncSession, active: ActiveExpedition
    ) -> None:
        """Если outcome не задан — выставить исход и финальные награды (как при claim)."""
        if getattr(active, "outcome", None) is not None:
            return
        et = int(getattr(active, "events_total", None) or 0)
        if et > 0:
            # v1.3: догнать пропущенные тики без ИИ (как в claim), затем исход по HP
            while int(active.events_done or 0) < et:
                await run_one_tick(session, active, silent=True)
            await session.flush()
            squad_rows: list = []
            for wid in list(active.squad_waifu_ids or []):
                w = await session.get(HiredWaifu, wid)
                if w and w.player_id == active.player_id:
                    squad_rows.append(w)
            outcome = _outcome_from_squad_hp_ratio(squad_rows)
            active.outcome = outcome
            mult = OUTCOME_REWARD_MULTIPLIERS[outcome]
            active.reward_gold = max(0, round(active.reward_gold * mult["gold"]))
            active.reward_experience = max(0, round(active.reward_experience * mult["exp"]))
            active.success = outcome == EXPEDITION_OUTCOME_SUCCESS
            return
        p_success = await _expedition_passive_p_success(session, int(active.player_id), active.chance)
        outcome = _roll_expedition_outcome(p_success)
        active.outcome = outcome
        mult = OUTCOME_REWARD_MULTIPLIERS[outcome]
        active.reward_gold = max(0, round(active.reward_gold * mult["gold"]))
        active.reward_experience = max(0, round(active.reward_experience * mult["exp"]))
        active.success = outcome == EXPEDITION_OUTCOME_SUCCESS

    async def _ensure_day_slots(
        self,
        session: AsyncSession,
        day,
        *,
        generation_nonce: str | None = None,
    ) -> list[ExpeditionSlot]:
        stmt = (
            select(ExpeditionSlot)
            .where(ExpeditionSlot.day == day)
            .order_by(ExpeditionSlot.slot)
        )
        existing = (await session.execute(stmt)).scalars().all()
        have = {int(s.slot) for s in existing}
        if generation_nonce:
            day_rng = random.Random(f"{day.isoformat()}-{generation_nonce}")
            trial_slot = (
                day_rng.randint(1, EXPEDITION_SLOTS_PER_DAY) if EXPEDITION_SLOTS_PER_DAY else 1
            )
        else:
            trial_slot = random.randint(1, EXPEDITION_SLOTS_PER_DAY) if EXPEDITION_SLOTS_PER_DAY else 1

        # Загружаем аффиксы из БД (ТЗ v1.1 / cursor_plan_6)
        affix_stmt = select(ExpeditionAffix).order_by(ExpeditionAffix.id)
        all_affixes = list((await session.execute(affix_stmt)).scalars().all())
        default_player_level = 10

        for slot_num in range(1, EXPEDITION_SLOTS_PER_DAY + 1):
            if slot_num in have:
                continue
            is_trial = slot_num == trial_slot
            target_difficulty = 5 if is_trial else {1: 1, 2: 3, 3: 5}.get(slot_num, 3)

            # 1. Архетип локации и режим экспедиции (нарративный слой)
            slot_seed = f"{day.isoformat()}-{slot_num}"
            if generation_nonce:
                slot_seed = f"{slot_seed}-{generation_nonce}"
            slot_rng = random.Random(slot_seed)
            archetype = pick_location_archetype(slot_rng)
            mode = pick_expedition_mode(slot_rng)
            base_name = archetype.name_ru
            biome_tag = archetype.biome_tag
            preview_name = slot_preview_name(mode, archetype)

            # 2. Подбор аффиксов до нужной суммы difficulty; лимит по количеству (лёгк 0–1, ср 2–3, тяж 4–5)
            max_affixes = 5 if is_trial else {1: 1, 2: 3, 3: 5}.get(slot_num, 3)
            remaining = min(target_difficulty - 1, max_affixes * 2)  # не набирать больше очков, чем нужно
            chosen: list[ExpeditionAffix] = []
            shuffled = list(all_affixes)
            slot_rng.shuffle(shuffled)
            for affix in shuffled:
                if remaining <= 0 or len(chosen) >= max_affixes:
                    break
                if affix.forbidden_biomes and biome_tag in (affix.forbidden_biomes or []):
                    continue
                if affix.allowed_biomes and biome_tag not in (affix.allowed_biomes or []):
                    continue
                if any(
                    a.type == affix.type and a.category == affix.category
                    for a in chosen
                ):
                    continue
                chosen.append(affix)
                remaining -= affix.difficulty_add
            chosen = chosen[:max_affixes]

            # Биом мог исключить все аффиксы — добираем без фильтра по биому (инвариант: непустой affix_ids).
            if not chosen and all_affixes:
                remaining_fb = min(target_difficulty - 1, max_affixes * 2)
                shuffled_fb = list(all_affixes)
                slot_rng.shuffle(shuffled_fb)
                for affix in shuffled_fb:
                    if remaining_fb <= 0 or len(chosen) >= max_affixes:
                        break
                    if any(
                        a.type == affix.type and a.category == affix.category
                        for a in chosen
                    ):
                        continue
                    chosen.append(affix)
                    remaining_fb -= affix.difficulty_add
                chosen = chosen[:max_affixes]

            # 3. Детерминированная сборка имени
            computed_name = _build_expedition_name(base_name, chosen)
            real_difficulty = 1 + sum(a.difficulty_add for a in chosen)
            total_damage_mult = 1.0
            total_reward_mult = 1.0
            all_paired: list[str] = []
            for a in chosen:
                total_damage_mult *= a.damage_mult
                total_reward_mult *= a.reward_mult
                all_paired.extend(a.paired_perks or [])
            paired_perks_list = list(dict.fromkeys(normalize_expedition_paired_perk_ids(all_paired)))
            slot_tags = tags_snapshot_for_affix_rows(chosen) if chosen else []

            slot_level = max(1, default_player_level - 5 + (real_difficulty - 1) * 2)
            base_gold = (
                EXPEDITION_BASE_GOLD
                + slot_level * 10
                + slot_rng.randint(0, 50)
                + (80 if is_trial else 0)
            )
            base_exp = (
                EXPEDITION_BASE_EXP
                + slot_level * 5
                + slot_rng.randint(0, 30)
                + (40 if is_trial else 0)
            )
            base_diff = 80 + slot_level * 5 + len(chosen) * 10 + (30 if is_trial else 0)

            session.add(
                ExpeditionSlot(
                    day=day,
                    slot=slot_num,
                    name=preview_name,
                    base_level=slot_level,
                    base_difficulty=base_diff,
                    affixes=[],
                    base_location=base_name,
                    affix_ids=[a.id for a in chosen],
                    computed_name=computed_name,
                    biome_tag=biome_tag,
                    difficulty=real_difficulty,
                    damage_mult=round(total_damage_mult, 2),
                    reward_mult=round(total_reward_mult, 2),
                    paired_perks=paired_perks_list,
                    difficulty_tags=slot_tags,
                    base_gold=base_gold,
                    base_experience=base_exp,
                    trial=is_trial,
                    location_archetype_id=archetype.id,
                    expedition_mode_id=mode.id,
                )
            )
        await session.flush()
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def admin_refresh_slots(self, session: AsyncSession) -> list[ExpeditionSlot]:
        """
        Админ: пересоздать слоты на сегодня с новым случайным содержимым (имитация полночного обновления).
        1) Автоматически «забирает» награды по всем экспедициям с ends_at <= now (висят незавершёнными).
        2) Обнуляет ссылку на слот у записей active_expeditions по слотам дня.
        3) Удаляет все слоты дня и создаёт 3 новых (уникальный generation_nonce).
        """
        today = _moscow_today()
        now = datetime.now(tz=timezone.utc)

        # ID слотов на сегодня (до любых удалений)
        today_slots_stmt = select(ExpeditionSlot.id).where(ExpeditionSlot.day == today)
        today_slot_ids = list((await session.execute(today_slots_stmt)).scalars().all())

        # Найти активные экспедиции по этим слотам, уже завершённые по времени, но не забранные
        if today_slot_ids:
            to_claim_stmt = (
                select(ActiveExpedition)
                .where(
                    ActiveExpedition.expedition_slot_id.in_(today_slot_ids),
                    ActiveExpedition.ends_at <= now,
                    ActiveExpedition.claimed.is_(False),
                    ActiveExpedition.cancelled.is_(False),
                )
            )
            to_claim = list((await session.execute(to_claim_stmt)).scalars().all())
            for active in to_claim:
                await self.claim(session, int(active.player_id), int(active.id))

        # Освободить ссылки на слоты дня (чтобы можно было удалить слоты)
        if today_slot_ids:
            await session.execute(
                update(ActiveExpedition)
                .where(ActiveExpedition.expedition_slot_id.in_(today_slot_ids))
                .values(expedition_slot_id=None)
            )

        # Удалить все слоты дня и создать 3 новых с уникальным seed (не как при том же day без nonce)
        await session.execute(delete(ExpeditionSlot).where(ExpeditionSlot.day == today))
        await session.flush()
        nonce = secrets.token_hex(8)
        return await self._ensure_day_slots(session, today, generation_nonce=nonce)
