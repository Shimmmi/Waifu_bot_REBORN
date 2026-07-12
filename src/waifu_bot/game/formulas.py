"""Game formulas and calculations."""
import math
import random

from typing import Any

from waifu_bot.game.constants import (
    ARMOR_DR_CAP,
    ARMOR_K_BASE,
    ARMOR_K_PER_LEVEL,
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
    PERFECTION_EXP_BASE,
    PERFECTION_EXP_LINEAR,
    PERFECTION_EXP_QUAD,
    PERFECTION_EXP_TIER_BUMP,
    RANGED_DAMAGE_COEFFICIENT,
    SPELL_DAMAGE_COEFFICIENT,
    STR_HP_COEFFICIENT,
    MediaType,
)


def calculate_max_hp(level: int, endurance: int, strength: int = 0) -> int:
    """Calculate maximum HP.

    Formula: BASE_HP_PER_LEVEL × level + ВЫН × 10 + СИЛ × 3
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


def calculate_armor_damage_reduction(armor_total: float, waifu_level: int) -> float:
    """Доля снижения от брони: A/(A+K(L)), кап ARMOR_DR_CAP."""
    a = max(0.0, float(armor_total))
    level = max(1, min(int(waifu_level or 1), int(MAX_LEVEL)))
    k = float(ARMOR_K_BASE) + float(ARMOR_K_PER_LEVEL) * float(level)
    if a + k <= 0:
        return 0.0
    return min(float(ARMOR_DR_CAP), a / (a + k))


def calculate_crit_multiplier(strength: int) -> float:
    """Crit multiplier = 1.5 + СИЛ × 0.01."""
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

    TEXT/LINK: (база × длина + статы по типу оружия) затем × коэффициент типа из MEDIA_COEFFICIENTS.

    Остальные медиа: база + ИНТ×INT_SKILL_DAMAGE_COEFF (без СИЛ/ЛОВ/ИНТ от оружия), затем × коэффициент типа.
    """
    media_coef = float(MEDIA_COEFFICIENTS.get(media_type, 1.0))
    base = int(weapon_damage) if weapon_damage is not None else int(BASE_SKILL_DAMAGE)

    length = max(0, int(message_length or 0))
    if media_type in (MediaType.TEXT, MediaType.LINK):
        length_cap = 200
        length_mult = 1.0 + (min(length, length_cap) / length_cap) * 0.5
    else:
        length_mult = 1.0

    if media_type in (MediaType.TEXT, MediaType.LINK):
        scaled = float(base) * length_mult
        core = calculate_damage(scaled, strength, agility, intelligence, attack_type)
        return int(core * media_coef)

    int_media = int(intelligence * INT_SKILL_DAMAGE_COEFF)
    core = base + int_media
    return int(core * media_coef)


def _stat_bonus_flat_for_attack(
    strength: int, agility: int, intelligence: int, attack_type: str
) -> tuple[float, str, str]:
    """Плоский бонус от основной характеристики и подпись для журнала."""
    if attack_type == "melee":
        return strength * MELEE_DAMAGE_COEFFICIENT, "СИЛ", "ближний бой"
    if attack_type == "ranged":
        return agility * RANGED_DAMAGE_COEFFICIENT, "ЛОВ", "дальний бой"
    if attack_type in ("magic", "spell"):
        return intelligence * SPELL_DAMAGE_COEFFICIENT, "ИНТ", "магия"
    return 0.0, "—", attack_type


def _media_type_label_ru(media_type: MediaType) -> str:
    return {
        MediaType.TEXT: "текст",
        MediaType.LINK: "ссылка",
        MediaType.STICKER: "стикер",
        MediaType.PHOTO: "фото",
        MediaType.GIF: "GIF",
        MediaType.AUDIO: "аудио",
        MediaType.VIDEO: "видео",
        MediaType.VOICE: "голос",
    }.get(media_type, "медиа")


def build_message_damage_base_trace_ru(
    media_type: MediaType,
    strength: int,
    agility: int,
    intelligence: int,
    attack_type: str,
    message_length: int,
    weapon_damage: int | None,
    weapon_main: int | None = None,
    weapon_offhand: int | None = None,
) -> tuple[int, list[dict[str, Any]]]:
    """Шаги базы урона сообщения в формате damage_breakdown; итог = calculate_message_damage(...)."""
    media_coef = float(MEDIA_COEFFICIENTS.get(media_type, 1.0))
    base = int(weapon_damage) if weapon_damage is not None else int(BASE_SKILL_DAMAGE)
    length = max(0, int(message_length or 0))
    if media_type in (MediaType.TEXT, MediaType.LINK):
        length_cap = 200
        length_mult = 1.0 + (min(length, length_cap) / length_cap) * 0.5
    else:
        length_mult = 1.0

    stat_bonus, stat_abbr, atk_ru = _stat_bonus_flat_for_attack(
        strength, agility, intelligence, attack_type
    )
    mt = _media_type_label_ru(media_type)
    steps: list[dict[str, Any]] = []
    if weapon_damage is not None:
        # Breakdown of the weapon base by hand, e.g. "= 20 (15MH+5OH)".
        parts: list[str] = []
        if weapon_main:
            parts.append(f"{int(weapon_main)}MH")
        if weapon_offhand:
            parts.append(f"{int(weapon_offhand)}OH")
        suffix = f" = {base} ({'+'.join(parts)})" if parts else f" = {base}"
        wpn_lbl = "База: урон оружия" + suffix
    else:
        wpn_lbl = "База: урон без оружия (навык)"
    steps.append(
        {
            "kind": "base",
            "source": "message_base",
            "label_ru": wpn_lbl,
            "value_before": 0,
            "value_after": base,
        }
    )

    if media_type in (MediaType.TEXT, MediaType.LINK):
        scaled = float(base) * length_mult
        scaled_int = int(scaled)
        dmg_core = calculate_damage(scaled, strength, agility, intelligence, attack_type)
        total = int(dmg_core * media_coef)

        if length_mult != 1.0:
            steps.append(
                {
                    "kind": "mult",
                    "source": "message_text_length",
                    "label_ru": f"Длина текста/ссылки: до +50% на 200 симв. (×{length_mult:.3f})",
                    "value_before": base,
                    "value_after": scaled_int,
                    "factor": round(length_mult, 6),
                }
            )
        steps.append(
            {
                "kind": "add",
                "source": "message_primary_stat",
                "label_ru": f"Урон от {stat_abbr} ({atk_ru}): +{int(stat_bonus)}",
                "value_before": scaled_int,
                "value_after": dmg_core,
                "delta": int(dmg_core - scaled_int),
            }
        )
        steps.append(
            {
                "kind": "mult",
                "source": "message_media_type",
                "label_ru": f"Коэффициент типа сообщения ({mt}): ×{media_coef:g}",
                "value_before": dmg_core,
                "value_after": total,
                "factor": round(media_coef, 6),
            }
        )
        return total, steps

    int_media_flat = int(intelligence * INT_SKILL_DAMAGE_COEFF)
    core = base + int_media_flat
    total = int(core * media_coef)

    if int_media_flat:
        steps.append(
            {
                "kind": "add",
                "source": "message_int_media",
                "label_ru": f"Урон от ИНТ к медиа: +{int_media_flat} (ИНТ × {INT_SKILL_DAMAGE_COEFF:g})",
                "value_before": base,
                "value_after": core,
                "delta": int_media_flat,
            }
        )
    steps.append(
        {
            "kind": "mult",
            "source": "message_media_type",
            "label_ru": f"Коэффициент типа сообщения ({mt}): ×{media_coef:g}",
            "value_before": core,
            "value_after": total,
            "factor": round(media_coef, 6),
        }
    )
    return total, steps


_ATTACK_TYPE_DAMAGE_FLAT_KEYS: dict[str, str] = {
    "melee": "melee_damage_flat",
    "ranged": "ranged_damage_flat",
    "magic": "magic_damage_flat",
    "spell": "magic_damage_flat",
}


def apply_equipment_damage_flats(
    damage: int,
    *,
    attack_type: str,
    media_type: MediaType,
    bonuses: dict[str, int],
) -> tuple[int, list[dict[str, Any]]]:
    """Плоские бонусы урона с экипировки (как в профиле «Подробно»).

    Текст/ссылка: damage_flat + бонус по типу оружия (melee/ranged/magic).
    Остальные медиа: damage_flat + magic_damage_flat (ветка урона от ИНТ).
    """
    from waifu_bot.game.affix_effect_ui import effect_stat_description_ru

    steps: list[dict[str, Any]] = []
    current = int(damage)
    keys_to_apply: list[str] = []

    if int(bonuses.get("damage_flat", 0) or 0):
        keys_to_apply.append("damage_flat")

    if media_type in (MediaType.TEXT, MediaType.LINK):
        type_key = _ATTACK_TYPE_DAMAGE_FLAT_KEYS.get((attack_type or "melee").lower())
        if type_key and int(bonuses.get(type_key, 0) or 0):
            keys_to_apply.append(type_key)
    elif int(bonuses.get("magic_damage_flat", 0) or 0):
        keys_to_apply.append("magic_damage_flat")

    for key in keys_to_apply:
        add = int(bonuses.get(key, 0) or 0)
        if not add:
            continue
        nb = current
        current = nb + add
        label = effect_stat_description_ru(key)
        steps.append(
            {
                "kind": "add",
                "source": "affix_attack_damage_flat",
                "label_ru": f"Экипировка: {label} +{add}",
                "value_before": nb,
                "value_after": current,
                "delta": add,
            }
        )

    pct = int(bonuses.get("damage_percent", 0) or 0)
    if pct:
        nb = current
        fac = 1.0 + pct / 100.0
        current = int(nb * fac)
        steps.append(
            {
                "kind": "mult",
                "source": "affix_attack_damage_percent",
                "label_ru": f"Экипировка: {effect_stat_description_ru('damage_percent')} +{pct}%",
                "value_before": nb,
                "value_after": current,
                "factor": round(fac, 6),
            }
        )

    return current, steps


def blend_rarity_weights_with_magic_find(opts: list[tuple[int, int]], total_mf_pct: float) -> list[tuple[int, int]]:
    """Смешать базовые веса редкости с целевым хвостом (15% эпик / 85% легенда при t=1).

    total_mf_pct — суммарный Magic Find в процентах (удача × LCK_MAGIC_FIND_COEFF×100 + экипировка).
    """
    from waifu_bot.game.constants import MAGIC_FIND_FULL_BLEND_PCT

    t = min(1.0, max(0.0, float(total_mf_pct) / float(MAGIC_FIND_FULL_BLEND_PCT)))
    base_w = {r: 0 for r in range(1, 6)}
    for r, w in opts:
        try:
            rr = int(r)
            ww = int(w)
        except Exception:
            continue
        if 1 <= rr <= 5 and ww > 0:
            base_w[rr] += ww
    total_b = sum(base_w.values())
    if total_b <= 0:
        base_w = {1: 70, 2: 25, 3: 5, 4: 0, 5: 0}
        total_b = 100
    bp = {r: base_w[r] / total_b for r in range(1, 6)}
    tp = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.15, 5: 0.85}
    scale = 10000
    blended: list[tuple[int, int]] = []
    for r in range(1, 6):
        p = (1.0 - t) * bp[r] + t * tp[r]
        w = max(0, int(round(p * scale)))
        if w > 0:
            blended.append((r, w))
    if not blended:
        return [(1, 1)]
    return blended


def calculate_crit_chance(agility: int, luck: int) -> float:
    """Calculate critical hit chance: УДЧ×0.1% (primary) + ЛОВ×0.1% (secondary). Cap 100%."""
    chance = (agility * CRIT_CHANCE_AGILITY) + (luck * CRIT_CHANCE_LUCK)
    return min(chance, CRIT_CHANCE_CAP)


def roll_crit(agility: int, luck: int) -> bool:
    """Roll for critical hit."""
    chance = calculate_crit_chance(agility, luck)
    return random.random() < chance


def get_crit_multiplier(strength: int = 0) -> float:
    """Get crit multiplier: 1.5 + СИЛ×0.01, randomised up to CRIT_MULTIPLIER_MAX."""
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


def calculate_perfection_experience_for_level(level: int) -> int:
    """XP needed to reach perfection level ``level`` from ``level - 1``.

    Level 1 is granted on hitting MAX_LEVEL; first grind is 1→2 (``level=2``).
    """
    if level <= 1:
        return 0
    n = int(level) - 1  # steps already completed before this transition
    return int(
        PERFECTION_EXP_BASE
        + PERFECTION_EXP_LINEAR * n
        + PERFECTION_EXP_QUAD * (n**2)
        + PERFECTION_EXP_TIER_BUMP * (n // 10)
    )


def calculate_total_perfection_experience_for_level(level: int) -> int:
    """Cumulative XP to reach perfection level from level 1 (after unlock grant)."""
    total = 0
    for lvl in range(2, int(level) + 1):
        total += calculate_perfection_experience_for_level(lvl)
    return total


# Доля от «цены выкупа у NPC» после скидки ОБА (до пассивок). Итоговая продажа в магазине = доля × цена после пассивок.
SHOP_SELL_VS_BUY_RATIO = 0.30


def shop_buy_price_from_merchant_discount(base_value: int, merchant_discount_pct: float) -> int:
    """Цена покупки у торговца: base × (1 − скидка%), скидка 0..50%."""
    d = max(0.0, min(50.0, float(merchant_discount_pct)))
    return max(1, int(int(base_value) * (1.0 - d / 100.0)))


def calculate_shop_price(base_value: int, charm: int, is_buy: bool = True) -> int:
    """Оценка цены только по числу ОБА (без flat с предметов). Для реального магазина см. ShopService."""
    from waifu_bot.game.constants import CHM_MERCHANT_DISCOUNT_COEFF

    discount_pct = max(0.0, min(50.0, float(charm) * float(CHM_MERCHANT_DISCOUNT_COEFF) * 100.0))
    buy_eq = shop_buy_price_from_merchant_discount(int(base_value), discount_pct)
    if is_buy:
        return buy_eq
    return max(1, int(buy_eq * SHOP_SELL_VS_BUY_RATIO))


def calculate_shop_sell_price(base_value: int, charm: int) -> int:
    """Цена скупки (charm-only): доля от эквивалента покупки при том же base_value."""
    return calculate_shop_price(base_value, charm, is_buy=False)


def calculate_gamble_price(level: int) -> int:
    """Calculate gamble price: min(10000, base + level * X)."""
    from waifu_bot.game.constants import GAMBLE_BASE_PRICE, GAMBLE_MAX_PRICE, GAMBLE_PRICE_PER_LEVEL

    price = GAMBLE_BASE_PRICE + (level * GAMBLE_PRICE_PER_LEVEL)
    return min(price, GAMBLE_MAX_PRICE)

