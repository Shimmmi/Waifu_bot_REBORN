"""Регрессия: баланс урона/крита/HP/магазина после правок констант (game/formulas.py)."""

from waifu_bot.game.constants import (
    CRIT_CHANCE_AGILITY,
    CRIT_CHANCE_CAP,
    CRIT_CHANCE_LUCK,
    DODGE_CHANCE_CAP,
    INT_EXP_BONUS_COEFF,
    INT_SKILL_DAMAGE_COEFF,
    MAGIC_FIND_FULL_BLEND_PCT,
    MediaType,
)
from waifu_bot.game.formulas import (
    blend_rarity_weights_with_magic_find,
    calculate_crit_chance,
    calculate_crit_multiplier,
    calculate_damage,
    calculate_dodge_chance,
    calculate_max_hp,
    calculate_message_damage,
    shop_buy_price_from_merchant_discount,
    SHOP_SELL_VS_BUY_RATIO,
)


def test_calculate_damage_flat_per_stat_one() -> None:
    assert calculate_damage(10, strength=10, agility=0, intelligence=0, attack_type="melee") == 20
    assert calculate_damage(10, strength=0, agility=7, intelligence=0, attack_type="ranged") == 17
    assert calculate_damage(10, strength=0, agility=0, intelligence=4, attack_type="magic") == 14


def test_calculate_max_hp_coefficients() -> None:
    assert calculate_max_hp(10, endurance=5, strength=3) == 20 * 10 + 5 * 10 + 3 * 3


def test_calculate_crit_multiplier_str_scaling() -> None:
    assert calculate_crit_multiplier(0) == 1.5
    assert calculate_crit_multiplier(100) == 1.5 + 100 * 0.01


def test_calculate_crit_chance_agility_luck() -> None:
    # 10 ЛОВ × 0.1% + 20 УДЧ × 0.1% = 3% (как доля 0.03)
    assert abs(calculate_crit_chance(10, 20) - (10 * CRIT_CHANCE_AGILITY + 20 * CRIT_CHANCE_LUCK)) < 1e-9


def test_calculate_crit_chance_capped_at_100pct() -> None:
    assert CRIT_CHANCE_CAP == 1.0
    assert calculate_crit_chance(5000, 5000) <= 1.0


def test_retaliation_dodge_fraction_matches_profile_without_gear_evade() -> None:
    """Реторс складывает ЛОВ dodge + sec evade; при 0 с экипа остаётся только ЛОВ — доля > 0."""
    base = calculate_dodge_chance(100, 0)
    assert base > 0
    gear_evade = 0.0
    dodge_frac = min(float(DODGE_CHANCE_CAP), min(1.0, base + gear_evade))
    assert dodge_frac == base


def test_blend_rarity_weights_mf_zero_preserves_base_shape() -> None:
    base = [(1, 70), (2, 25), (3, 5)]
    out = blend_rarity_weights_with_magic_find(base, 0.0)
    d = {r: w for r, w in out}
    assert sum(d.values()) == 10000
    assert d[1] > d[2] > d[3]


def test_blend_rarity_weights_high_mf_favors_high_rarity() -> None:
    base = [(1, 70), (2, 25), (3, 5)]
    out = blend_rarity_weights_with_magic_find(base, float(MAGIC_FIND_FULL_BLEND_PCT))
    d = {r: w for r, w in out}
    assert d.get(5, 0) > d.get(1, 0)
    assert d.get(4, 0) > 0


def test_calculate_message_damage_int_bonus_non_text_media() -> None:
    # sticker: база + ИНТ×INT_SKILL_DAMAGE_COEFF, затем × MEDIA_COEFFICIENTS (без СИЛ/ЛОВ/ИНТ от оружия)
    d = calculate_message_damage(
        MediaType.STICKER,
        strength=10,
        agility=0,
        intelligence=5,
        attack_type="melee",
        message_length=0,
        weapon_damage=10,
    )
    core = 10 + int(5 * INT_SKILL_DAMAGE_COEFF)
    assert d == int(core * 0.9)


def test_shop_buy_sell_ratio() -> None:
    base = 1000
    buy = shop_buy_price_from_merchant_discount(base, 20.0)
    assert buy == 800
    sell = int(buy * SHOP_SELL_VS_BUY_RATIO)
    assert sell == 240


def test_int_exp_coeff_defined() -> None:
    assert INT_EXP_BONUS_COEFF == 0.001
    assert INT_SKILL_DAMAGE_COEFF == 1.0
