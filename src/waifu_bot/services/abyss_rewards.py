"""Abyss (Бездна) scaling formulas, floor modifiers, biomes and reward math.

Pure, config-driven helpers (no DB / no I/O) so they can be unit-tested in
isolation. `cfg` is the dict returned by `get_game_config_map(session)`.
"""
from __future__ import annotations

import math
import random

from waifu_bot.game.constants import INT_EXP_BONUS_COEFF, LCK_GOLD_COEFF
from waifu_bot.services.game_config_service import cfg_float, cfg_int

# ---------------------------------------------------------------------------
# Floor modifiers
# ---------------------------------------------------------------------------

ABYSS_MODIFIERS = ("BLESSED", "CURSED", "RAGE", "DARK", "ECHO")

MODIFIER_ICONS: dict[str, str] = {
    "BLESSED": "✨",
    "CURSED": "💀",
    "RAGE": "🔥",
    "DARK": "🌑",
    "ECHO": "👻",
}

MODIFIER_LABELS: dict[str, str] = {
    "BLESSED": "Благословение",
    "CURSED": "Проклятие",
    "RAGE": "Ярость",
    "DARK": "Тьма",
    "ECHO": "Эхо",
}

MODIFIER_DESCRIPTIONS: dict[str, str] = {
    "BLESSED": "Золото и опыт ×1.5",
    "CURSED": "Стикеры не наносят урон",
    "RAGE": "Урон монстров ×2, но награды ×1.5",
    "DARK": "Медиа-сообщения не наносят урон",
    "ECHO": "Тень убитого босса кампании, +20% опыта",
}


# ---------------------------------------------------------------------------
# Pseudo-biomes (monster pool tags per floor range)
# ---------------------------------------------------------------------------

ABYSS_BIOMES: dict[tuple[int, int], list[str]] = {
    (1, 20): ["cave", "undead"],
    (21, 40): ["forest", "beast", "cave"],
    (41, 60): ["fortress", "demon", "cursed"],
    (61, 80): ["elemental", "construct", "cursed"],
    (81, 100): ["dragon", "demon", "elemental"],
}

_DEEP_BIOME_TAGS = ["cave", "undead", "demon", "elemental", "dragon", "fae"]


def get_abyss_biome_tags(floor: int) -> list[str]:
    """Return monster pool tags for the floor's pseudo-biome (101+ = all)."""
    for (start, end), tags in ABYSS_BIOMES.items():
        if start <= floor <= end:
            return list(tags)
    return list(_DEEP_BIOME_TAGS)


def is_checkpoint(floor: int) -> bool:
    """A checkpoint floor is any positive floor divisible by 10."""
    return floor > 0 and floor % 10 == 0


# ---------------------------------------------------------------------------
# Monster stat scaling (F = floor number)
# ---------------------------------------------------------------------------

def calc_abyss_monster_hp(cfg: dict[str, str], base_hp: int, floor: int) -> int:
    k = cfg_float(cfg, "abyss_hp_scale_linear", 0.15)
    e = cfg_float(cfg, "abyss_hp_scale_exp", 1.2)
    return max(1, round(base_hp * ((1 + floor * k) ** e)))


def calc_abyss_monster_dmg(cfg: dict[str, str], base_dmg: int, floor: int) -> int:
    k = cfg_float(cfg, "abyss_dmg_scale_linear", 0.10)
    e = cfg_float(cfg, "abyss_dmg_scale_exp", 1.1)
    return max(1, round(base_dmg * ((1 + floor * k) ** e)))


def calc_abyss_monster_exp(cfg: dict[str, str], base_exp: int, floor: int) -> int:
    k = cfg_float(cfg, "abyss_exp_scale_linear", 0.12)
    return max(1, round(base_exp * (1 + floor * k)))


def calc_abyss_gold(cfg: dict[str, str], base_gold: int, floor: int) -> tuple[int, int]:
    """Return (min_gold, max_gold) for an ordinary monster on this floor."""
    k = cfg_float(cfg, "abyss_gold_scale_linear", 0.08)
    avg = round(base_gold * (1 + floor * k))
    return (max(1, round(avg * 0.8)), max(1, round(avg * 1.2)))


def calc_abyss_item_level(cfg: dict[str, str], floor: int) -> int:
    d = max(1, cfg_int(cfg, "abyss_item_level_divisor", 2))
    return max(1, math.ceil(floor / d))


def calc_abyss_elite_chance(cfg: dict[str, str], floor: int) -> float:
    base = cfg_float(cfg, "abyss_elite_chance_base", 0.10)
    per_floor = cfg_float(cfg, "abyss_elite_floor_bonus", 0.002)
    cap = cfg_float(cfg, "abyss_elite_chance_max", 0.40)
    return min(base + floor * per_floor, cap)


def calc_checkpoint_shards(cfg: dict[str, str], floor: int) -> int:
    """Shards awarded for clearing a checkpoint = (floor/10) * per_checkpoint."""
    per_cp = cfg_int(cfg, "abyss_shards_per_checkpoint", 10)
    boss_mult = cfg_float(cfg, "abyss_shards_boss_mult", 1.0)
    checkpoint_num = max(1, floor // 10)
    return max(0, round(checkpoint_num * per_cp * boss_mult))


# ---------------------------------------------------------------------------
# Luck / INT reward bonuses (reused from the main combat formulas)
# ---------------------------------------------------------------------------

def apply_luck_gold_bonus(gold: int, luck: int) -> int:
    """Gold *= 1 + УДЧ × LCK_GOLD_COEFF (mirrors solo-dungeon reward math)."""
    return round(gold * (1.0 + max(0, int(luck)) * LCK_GOLD_COEFF))


def apply_int_exp_bonus(exp: int, intelligence: int) -> int:
    """EXP *= 1 + ИНТ × INT_EXP_BONUS_COEFF."""
    return round(exp * (1.0 + max(0, int(intelligence)) * INT_EXP_BONUS_COEFF))


# ---------------------------------------------------------------------------
# Modifier assignment
# ---------------------------------------------------------------------------

def should_assign_modifier(
    cfg: dict[str, str],
    floor: int,
    last_modifier_floor: int,
    rng: random.Random | None = None,
) -> bool:
    """Decide whether the given (non-checkpoint) floor gets a modifier."""
    rng = rng or random
    if floor < cfg_int(cfg, "abyss_modifier_start_floor", 5):
        return False
    if is_checkpoint(floor):
        return False
    min_gap = cfg_int(cfg, "abyss_modifier_min_floor_gap", 3)
    max_gap = cfg_int(cfg, "abyss_modifier_max_floor_gap", 5)
    floors_since_last = floor - int(last_modifier_floor or 0)
    if floors_since_last < min_gap:
        return False
    if floors_since_last >= max_gap:
        return True
    return rng.random() < 0.5


def pick_modifier(cfg: dict[str, str], rng: random.Random | None = None) -> str | None:
    """Weighted random pick among modifiers (or None)."""
    rng = rng or random
    weights: dict[str | None, int] = {
        "BLESSED": cfg_int(cfg, "abyss_modifier_weight_blessed", 20),
        "CURSED": cfg_int(cfg, "abyss_modifier_weight_cursed", 15),
        "RAGE": cfg_int(cfg, "abyss_modifier_weight_rage", 15),
        "DARK": cfg_int(cfg, "abyss_modifier_weight_dark", 15),
        "ECHO": cfg_int(cfg, "abyss_modifier_weight_echo", 20),
        None: cfg_int(cfg, "abyss_modifier_weight_none", 15),
    }
    keys = list(weights.keys())
    vals = list(weights.values())
    if sum(vals) <= 0:
        return None
    return rng.choices(keys, weights=vals)[0]


def modifier_label(modifier: str | None) -> str | None:
    if not modifier:
        return None
    icon = MODIFIER_ICONS.get(modifier, "")
    label = MODIFIER_LABELS.get(modifier, modifier)
    return f"{icon} {label}".strip()


# ---------------------------------------------------------------------------
# Reward computation (modifier-aware; Grace applied by the caller)
# ---------------------------------------------------------------------------

def apply_modifier_to_gold(cfg: dict[str, str], gold: int, modifier: str | None) -> int:
    if modifier == "BLESSED":
        gold = round(gold * cfg_float(cfg, "abyss_modifier_blessed_gold", 1.5))
    elif modifier == "RAGE":
        gold = round(gold * cfg_float(cfg, "abyss_modifier_rage_reward", 1.5))
    return gold


def apply_modifier_to_exp(cfg: dict[str, str], exp: int, modifier: str | None) -> int:
    if modifier in ("BLESSED", "ECHO"):
        exp = round(exp * cfg_float(cfg, "abyss_modifier_blessed_gold", 1.5))
    if modifier == "RAGE":
        exp = round(exp * cfg_float(cfg, "abyss_modifier_rage_reward", 1.5))
    return exp


def calc_monster_gold(
    cfg: dict[str, str],
    floor: int,
    luck: int,
    modifier: str | None,
    rng: random.Random | None = None,
) -> int:
    """Base monster gold incl. luck bonus and floor modifier (no Grace)."""
    rng = rng or random
    base = cfg_int(cfg, "abyss_gold_base", 20)
    gold_min, gold_max = calc_abyss_gold(cfg, base, floor)
    gold = rng.randint(gold_min, gold_max)
    gold = apply_luck_gold_bonus(gold, luck)
    return apply_modifier_to_gold(cfg, gold, modifier)


def calc_monster_exp(
    cfg: dict[str, str],
    floor: int,
    intelligence: int,
    modifier: str | None,
) -> int:
    """Base monster EXP incl. INT bonus and floor modifier (no Grace)."""
    base = cfg_int(cfg, "abyss_monster_exp_base", 50)
    exp = calc_abyss_monster_exp(cfg, base, floor)
    exp = apply_int_exp_bonus(exp, intelligence)
    return apply_modifier_to_exp(cfg, exp, modifier)
