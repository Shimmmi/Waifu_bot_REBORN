"""Экспедиции v2: тип награды, тиры глубины, мощь отряда, процедурная генерация."""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from waifu_bot.db.models.waifu import WaifuRarity

REWARD_TYPES: tuple[str, ...] = (
    "gold",
    "waifu_exp",
    "items",
    "enchant",
    "merc_exp",
    "mixed",
)

REWARD_TYPE_LABELS_RU: dict[str, str] = {
    "gold": "Золото",
    "waifu_exp": "Опыт основной вайфу",
    "items": "Снаряжение",
    "enchant": "Камни заточки",
    "merc_exp": "Опыт наёмниц",
    "mixed": "Смешанная добыча",
}

# База мощи по редкости + рост за уровень
POWER_RARITY_BASE: dict[int, int] = {
    int(WaifuRarity.COMMON): 40,
    int(WaifuRarity.UNCOMMON): 55,
    int(WaifuRarity.RARE): 75,
    int(WaifuRarity.EPIC): 95,
    int(WaifuRarity.LEGENDARY): 120,
}
POWER_PER_LEVEL = 3


@dataclass(frozen=True)
class DepthTier:
    tier: int
    name_ru: str
    min_squad_power: int
    events_count: int
    duration_minutes: int
    reward_mult: float
    damage_mult: float
    difficulty_level: int  # 1..5 для AFFIX_LEVEL_BASE_HP_PCT


DEPTH_TIERS: tuple[DepthTier, ...] = (
    DepthTier(1, "Разведка", 0, 2, 30, 0.70, 0.85, 1),
    DepthTier(2, "Патруль", 80, 3, 45, 0.90, 0.95, 2),
    DepthTier(3, "Поход", 150, 4, 60, 1.00, 1.00, 3),
    DepthTier(4, "Рейд", 220, 6, 90, 1.25, 1.10, 4),
    DepthTier(5, "Экспедиция в глубину", 300, 8, 120, 1.50, 1.20, 5),
)

MIXED_REWARD_PENALTY = 0.55  # каждая часть смешанной награды


def compute_hired_power(level: int, rarity: int) -> int:
    """Мощь наёмницы: база редкости + рост с уровнем."""
    lv = max(1, int(level or 1))
    r = int(rarity or int(WaifuRarity.COMMON))
    base = POWER_RARITY_BASE.get(r, 40)
    return base + (lv - 1) * POWER_PER_LEVEL


def squad_power_total(units: list[Any]) -> int:
    total = 0
    for u in units:
        p = getattr(u, "power", None)
        if p is not None and int(p) > 0:
            total += int(p)
        else:
            total += compute_hired_power(
                int(getattr(u, "level", 1) or 1),
                int(getattr(u, "rarity", 1) or 1),
            )
    return total


def depth_tier_by_id(tier: int) -> DepthTier | None:
    t = int(tier)
    for dt in DEPTH_TIERS:
        if dt.tier == t:
            return dt
    return None


def depth_tier_catalog() -> list[dict[str, Any]]:
    return [
        {
            "tier": dt.tier,
            "name": dt.name_ru,
            "min_squad_power": dt.min_squad_power,
            "events_count": dt.events_count,
            "duration_minutes": dt.duration_minutes,
            "reward_mult": dt.reward_mult,
            "damage_mult": dt.damage_mult,
            "difficulty_level": dt.difficulty_level,
        }
        for dt in DEPTH_TIERS
    ]


def reward_type_catalog() -> list[dict[str, str]]:
    return [{"id": rt, "name": REWARD_TYPE_LABELS_RU[rt]} for rt in REWARD_TYPES]


def validate_reward_type(reward_type: str | None) -> str | None:
    rt = str(reward_type or "").strip().lower()
    if rt not in REWARD_TYPES:
        return None
    return rt


def base_reward_amount(reward_type: str, *, depth: DepthTier, player_level: int = 10) -> int:
    """Базовое значение награды до outcome/passive множителей."""
    lv = max(1, int(player_level))
    if reward_type == "gold":
        return max(50, int(80 + lv * 4) * depth.reward_mult)
    if reward_type == "waifu_exp":
        return max(30, int(40 + lv * 3) * depth.reward_mult)
    if reward_type == "items":
        return 1  # count
    if reward_type == "enchant":
        return max(1, int(round((1 + depth.tier // 2) * depth.reward_mult)))
    if reward_type == "merc_exp":
        return max(40, int(50 + lv * 2) * depth.reward_mult)
    if reward_type == "mixed":
        return max(40, int(60 + lv * 2) * depth.reward_mult * MIXED_REWARD_PENALTY)
    return 0


# Лечение: минуты на 1% недостающего HP (без бесплатной регенерации)
HEAL_MINUTES_PER_HP_PCT = 0.8
HEAL_MIN_MINUTES = 5
HEAL_MAX_MINUTES = 480


def heal_duration_minutes(current_hp: int, max_hp: int) -> int:
    mx = max(1, int(max_hp))
    cur = max(0, min(mx, int(current_hp)))
    missing_pct = (mx - cur) / float(mx) * 100.0
    if missing_pct <= 0:
        return 0
    minutes = int(round(missing_pct * HEAL_MINUTES_PER_HP_PCT))
    if cur <= 0:
        minutes = int(round(minutes * 1.5))
    return max(HEAL_MIN_MINUTES, min(HEAL_MAX_MINUTES, minutes))


def interpolate_heal_hp(
    *,
    heal_start_hp: int,
    max_hp: int,
    heal_started_at,
    heal_complete_at,
    now,
) -> int:
    """Текущее HP с учётом активного лечения (линейная интерполяция)."""
    mx = max(1, int(max_hp))
    if heal_started_at is None or heal_complete_at is None:
        return max(0, min(mx, int(heal_start_hp if heal_start_hp is not None else mx)))
    if now >= heal_complete_at:
        return mx
    if now <= heal_started_at:
        return max(0, min(mx, int(heal_start_hp or 0)))
    start_hp = max(0, min(mx, int(heal_start_hp or 0)))
    total = (heal_complete_at - heal_started_at).total_seconds()
    if total <= 0:
        return mx
    elapsed = (now - heal_started_at).total_seconds()
    frac = min(1.0, max(0.0, elapsed / total))
    return max(start_hp, min(mx, int(round(start_hp + (mx - start_hp) * frac))))


def is_healing(waifu: Any, now) -> bool:
    complete = getattr(waifu, "heal_complete_at", None)
    if complete is None:
        return False
    return now < complete


def gate_log_entry(
    *,
    event_index: int,
    category: str,
    damage: int,
    covered: bool,
    outcome_hint: str = "",
    base_pct: float | None = None,
    tag_mult: float | None = None,
    challenge_adj: float | None = None,
    variance: float | None = None,
    twist: str = "",
    active_tags: list[str] | None = None,
    covered_tags: list[str] | None = None,
    coverage: float | None = None,
) -> dict[str, Any]:
    from waifu_bot.game.expedition_difficulty_tags import DIFFICULTY_TAG_LABEL_RU

    cat_label = DIFFICULTY_TAG_LABEL_RU.get(category, category)
    status = "пройдено" if covered else "урон"
    text = f"{cat_label}: {status}"
    if damage > 0:
        text += f" (−{damage} HP)"
    if twist:
        text += f" — {twist}"
    if outcome_hint:
        text += f" — {outcome_hint}"
    entry: dict[str, Any] = {
        "index": event_index,
        "category": category,
        "category_label": cat_label,
        "damage": damage,
        "covered": covered,
        "text": text,
    }
    if base_pct is not None:
        entry["base_pct"] = round(float(base_pct) * 100.0, 1)
    if tag_mult is not None:
        entry["tag_mult"] = round(float(tag_mult), 3)
    if challenge_adj is not None:
        entry["challenge_adj"] = round(float(challenge_adj), 3)
    if variance is not None:
        entry["variance"] = round(float(variance), 3)
    if twist:
        entry["twist"] = twist
    if active_tags is not None:
        entry["active_tags"] = list(active_tags)
    if covered_tags is not None:
        entry["covered_tags"] = list(covered_tags)
    if coverage is not None:
        entry["coverage"] = round(float(coverage), 3)
    return entry


def pick_procedural_affixes(all_affixes: list[Any], rng: random.Random, count: int = 2) -> list[Any]:
    """Случайный набор аффиксов для процедурной экспедиции."""
    if not all_affixes:
        return []
    n = max(1, min(count, len(all_affixes)))
    return rng.sample(list(all_affixes), k=n)
