"""Game formulas and calculations."""
import random

from waifu_bot.game.constants import (
    BASE_HP_PER_LEVEL,
    BASE_SKILL_DAMAGE,
    CRIT_CHANCE_AGILITY,
    CRIT_CHANCE_LUCK,
    CRIT_MULTIPLIER_MAX,
    CRIT_MULTIPLIER_MIN,
    DODGE_CHANCE_AGILITY,
    DODGE_CHANCE_LUCK,
    EXP_BASE,
    EXP_MULTIPLIER,
    HP_K_COEFFICIENT,
    MAX_LEVEL,
    MELEE_DAMAGE_COEFFICIENT,
    MEDIA_COEFFICIENTS,
    RANGED_DAMAGE_COEFFICIENT,
    SPELL_DAMAGE_COEFFICIENT,
    MediaType,
)


def calculate_max_hp(level: int, endurance: int) -> int:
    """Calculate maximum HP: base_hp(level) + ВЫН * k_hp."""
    base_hp = BASE_HP_PER_LEVEL * level
    endurance_bonus = endurance * HP_K_COEFFICIENT
    return int(base_hp + endurance_bonus)


def calculate_damage(
    base_damage: int,
    strength: int = 0,
    agility: int = 0,
    intelligence: int = 0,
    attack_type: str = "melee",
) -> int:
    """Calculate damage based on weapon and stats."""
    if attack_type == "melee":
        stat_bonus = strength * MELEE_DAMAGE_COEFFICIENT
    elif attack_type == "ranged":
        stat_bonus = agility * RANGED_DAMAGE_COEFFICIENT
    elif attack_type == "magic" or attack_type == "spell":
        stat_bonus = intelligence * SPELL_DAMAGE_COEFFICIENT
    else:
        stat_bonus = 0

    return int(base_damage * (1 + stat_bonus))


def calculate_message_damage(
    media_type: MediaType,
    strength: int = 0,
    agility: int = 0,
    intelligence: int = 0,
    attack_type: str = "melee",
) -> int:
    """Calculate damage from message: base_skill_damage * media_coef * (1 + stat_bonuses)."""
    media_coef = MEDIA_COEFFICIENTS.get(media_type, 1.0)
    base_damage = BASE_SKILL_DAMAGE * media_coef

    return calculate_damage(base_damage, strength, agility, intelligence, attack_type)


def calculate_crit_chance(agility: int, luck: int) -> float:
    """Calculate critical hit chance: ЛОВ*0.4% + УДЧ*0.2%."""
    chance = (agility * CRIT_CHANCE_AGILITY) + (luck * CRIT_CHANCE_LUCK)
    return min(chance, 0.95)  # Cap at 95%


def roll_crit(agility: int, luck: int) -> bool:
    """Roll for critical hit."""
    chance = calculate_crit_chance(agility, luck)
    return random.random() < chance


def get_crit_multiplier() -> float:
    """Get random crit multiplier between 1.5x and 2.0x."""
    return random.uniform(CRIT_MULTIPLIER_MIN, CRIT_MULTIPLIER_MAX)


def calculate_dodge_chance(agility: int, luck: int) -> float:
    """Calculate dodge chance: ЛОВ*0.2% + УДЧ*0.1%."""
    chance = (agility * DODGE_CHANCE_AGILITY) + (luck * DODGE_CHANCE_LUCK)
    return min(chance, 0.90)  # Cap at 90%


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
    
    Buy: 110-200% of base (higher charm = lower price)
    Sell: 50-90% of base (higher charm = higher price)
    """
    # Charm range: 10-50 (typical), normalize to 0-1
    charm_normalized = max(0, min(1, (charm - 10) / 40))

    if is_buy:
        # Higher charm = lower price (110% to 200%)
        multiplier = 2.0 - (charm_normalized * 0.9)  # 2.0 to 1.1
    else:
        # Higher charm = higher sell price (50% to 90%)
        multiplier = 0.5 + (charm_normalized * 0.4)  # 0.5 to 0.9

    return int(base_value * multiplier)


def calculate_gamble_price(level: int) -> int:
    """Calculate gamble price: min(10000, base + level * X)."""
    from waifu_bot.game.constants import GAMBLE_BASE_PRICE, GAMBLE_MAX_PRICE, GAMBLE_PRICE_PER_LEVEL

    price = GAMBLE_BASE_PRICE + (level * GAMBLE_PRICE_PER_LEVEL)
    return min(price, GAMBLE_MAX_PRICE)

