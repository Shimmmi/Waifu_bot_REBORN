"""Game formulas and calculations."""
import math
import random

from waifu_bot.game.constants import (
    BASE_HP_PER_LEVEL,
    BASE_SKILL_DAMAGE,
    CRIT_CHANCE_AGILITY,
    CRIT_CHANCE_CAP,
    CRIT_CHANCE_LUCK,
    CRIT_MULTIPLIER_BASE,
    CRIT_MULTIPLIER_MAX,
    CRIT_MULTIPLIER_MIN,
    CRIT_MULTIPLIER_PER_STR,
    DODGE_CHANCE_AGILITY,
    DODGE_CHANCE_CAP,
    DODGE_CHANCE_LUCK,
    EXP_BASE,
    EXP_MULTIPLIER,
    HP_K_COEFFICIENT,
    HP_REGEN_END_DIVISOR,
    HP_REGEN_OUT_OF_COMBAT_MULT,
    INT_EXP_BONUS_COEFF,
    INT_SKILL_DAMAGE_COEFF,
    MAX_ENERGY,
    END_DAMAGE_REDUCTION_COEFF,
    END_DAMAGE_REDUCTION_CAP,
    END_ENERGY_COEFF,
    LCK_GOLD_COEFF,
    LCK_ITEM_DROP_COEFF,
    MAX_LEVEL,
    MELEE_DAMAGE_COEFFICIENT,
    MEDIA_COEFFICIENTS,
    RANGED_DAMAGE_COEFFICIENT,
    SPELL_DAMAGE_COEFFICIENT,
    STR_HP_COEFFICIENT,
    MediaType,
)


def calculate_max_hp(level: int, endurance: int, strength: int = 0) -> int:
    """Calculate maximum HP.

    Formula: BASE_HP_PER_LEVEL × level + ВЫН × 5 + СИЛ × 2
    """
    base_hp = BASE_HP_PER_LEVEL * level
    endurance_bonus = endurance * HP_K_COEFFICIENT
    strength_bonus = strength * STR_HP_COEFFICIENT
    return int(base_hp + endurance_bonus + strength_bonus)


def calculate_max_energy(endurance: int) -> int:
    """Calculate maximum energy: MAX_ENERGY + ВЫН × END_ENERGY_COEFF."""
    return int(MAX_ENERGY + endurance * END_ENERGY_COEFF)


def calculate_damage_reduction(endurance: int) -> float:
    """Calculate incoming damage reduction from ВЫН. Capped at END_DAMAGE_REDUCTION_CAP."""
    return min(endurance * END_DAMAGE_REDUCTION_COEFF, END_DAMAGE_REDUCTION_CAP)


def calculate_crit_multiplier(strength: int) -> float:
    """Crit multiplier = 1.5 + СИЛ × 0.005."""
    return CRIT_MULTIPLIER_BASE + strength * CRIT_MULTIPLIER_PER_STR


def calculate_hp_regen_rate(max_hp: int, endurance: int, in_combat: bool = True) -> float:
    """Calculate HP regeneration per hour.

    Formula: HP_max × (1 − e^(−END/100)) [per hour]
    Outside dungeon: × HP_REGEN_OUT_OF_COMBAT_MULT (×5)
    """
    base_rate = max_hp * (1.0 - math.exp(-endurance / HP_REGEN_END_DIVISOR))
    if not in_combat:
        base_rate *= HP_REGEN_OUT_OF_COMBAT_MULT
    return base_rate


def calculate_damage(
    base_damage: int,
    strength: int = 0,
    agility: int = 0,
    intelligence: int = 0,
    attack_type: str = "melee",
) -> int:
    """Calculate damage based on weapon and stats.

    Formula: base_damage + flat_stat_bonus
    Each point of the primary stat adds COEFFICIENT flat damage (currently 1.0).
    This matches the profile UI which shows "+N к урону" per stat point.
    """
    if attack_type == "melee":
        stat_bonus = strength * MELEE_DAMAGE_COEFFICIENT
    elif attack_type == "ranged":
        stat_bonus = agility * RANGED_DAMAGE_COEFFICIENT
    elif attack_type == "magic" or attack_type == "spell":
        stat_bonus = intelligence * SPELL_DAMAGE_COEFFICIENT
    else:
        stat_bonus = 0

    return int(base_damage + stat_bonus)


def calculate_message_damage(
    media_type: MediaType,
    strength: int = 0,
    agility: int = 0,
    intelligence: int = 0,
    attack_type: str = "melee",
    message_length: int = 0,
    weapon_damage: int | None = None,
) -> int:
    """Calculate damage from message.

    Components:
    - base = weapon_damage (if provided) else BASE_SKILL_DAMAGE
    - media multiplier depends on MediaType
    - length multiplier (text/link only) gives small scaling with message length (capped)
    - stat scaling depends on attack_type (strength/agility/intelligence)
    """
    media_coef = MEDIA_COEFFICIENTS.get(media_type, 1.0)
    base = int(weapon_damage) if weapon_damage is not None else int(BASE_SKILL_DAMAGE)

    # Only scale with length for text-like actions
    length = max(0, int(message_length or 0))
    if media_type in (MediaType.TEXT, MediaType.LINK):
        # Up to +50% at 200 chars (then capped)
        length_cap = 200
        length_mult = 1.0 + (min(length, length_cap) / length_cap) * 0.5
    else:
        length_mult = 1.0

    base_damage = base * media_coef * length_mult

    return calculate_damage(base_damage, strength, agility, intelligence, attack_type)


def calculate_crit_chance(agility: int, luck: int) -> float:
    """Calculate critical hit chance: УДЧ×0.1% (primary) + ЛОВ×0.05% (secondary). Cap 50%."""
    chance = (agility * CRIT_CHANCE_AGILITY) + (luck * CRIT_CHANCE_LUCK)
    return min(chance, CRIT_CHANCE_CAP)


def roll_crit(agility: int, luck: int) -> bool:
    """Roll for critical hit."""
    chance = calculate_crit_chance(agility, luck)
    return random.random() < chance


def get_crit_multiplier(strength: int = 0) -> float:
    """Get crit multiplier: 1.5 + СИЛ×0.005, randomised up to CRIT_MULTIPLIER_MAX."""
    base = calculate_crit_multiplier(strength)
    upper = max(base, CRIT_MULTIPLIER_MAX)
    return random.uniform(base, upper)


def calculate_dodge_chance(agility: int, luck: int = 0) -> float:
    """Calculate dodge chance: ЛОВ×0.1%. Cap 40%."""
    chance = (agility * DODGE_CHANCE_AGILITY) + (luck * DODGE_CHANCE_LUCK)
    return min(chance, DODGE_CHANCE_CAP)


def roll_dodge(agility: int, luck: int) -> bool:
    """Roll for dodge."""
    chance = calculate_dodge_chance(agility, luck)
    return random.random() < chance


def calculate_experience_for_level(level: int) -> int:
    """Calculate experience required to reach level from level-1."""
    if level <= 1:
        return 0
    return int(EXP_BASE * (level ** EXP_MULTIPLIER))


def calculate_total_experience_for_level(level: int) -> int:
    """Calculate total experience required to reach level from level 1."""
    total = 0
    for lvl in range(2, level + 1):
        total += calculate_experience_for_level(lvl)
    return total


def calculate_shop_price(base_value: int, charm: int, is_buy: bool = True) -> int:
    """Calculate shop price based on charm (ОБА).

    IMPORTANT: align with profile's merchant_discount:
      merchant_discount% = clamp((charm - 10) * 1%, 0..50%)

    - Buy: base * (1 - discount%)
    - Sell: base * (0.5..0.9) scaled by the same discount% (keeps legacy bounds)
    """
    discount_pct = max(0.0, min(50.0, (float(charm) - 10.0) * 1.0))

    if is_buy:
        multiplier = 1.0 - (discount_pct / 100.0)  # 1.00 .. 0.50
    else:
        # Keep 0.5..0.9 range, but drive it from the same %.
        multiplier = 0.5 + (discount_pct / 50.0) * 0.4  # 0.5 .. 0.9

    return int(int(base_value) * multiplier)


def calculate_gamble_price(level: int) -> int:
    """Calculate gamble price: min(10000, base + level * X)."""
    from waifu_bot.game.constants import GAMBLE_BASE_PRICE, GAMBLE_MAX_PRICE, GAMBLE_PRICE_PER_LEVEL

    price = GAMBLE_BASE_PRICE + (level * GAMBLE_PRICE_PER_LEVEL)
    return min(price, GAMBLE_MAX_PRICE)

