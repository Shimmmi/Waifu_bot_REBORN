"""Каталог бонусов системы Совершенствования (post-60)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

WeightClass = Literal["resource", "primary", "hp", "secondary", "combat_dmg", "situational"]
BonusKind = Literal["permanent", "instant"]
# unit:
#   "" | "HP" | "золото" | "пыль" | "камни" | "HP/мин" — абсолютные
#   "%" — secondary fraction в бою (store = raw/100)
#   "combat_pct" — целые % для damage pool (store = raw as int)


@dataclass(frozen=True)
class PerfectionBonusDef:
    id: str
    title_ru: str
    kind: BonusKind
    weight_class: WeightClass
    values_by_tier: tuple[float, ...]
    unit: str = ""
    # Ключ в combat eff_bonuses (если отличается от id)
    combat_key: str | None = None


TIER_COUNT = 10

PRIMARY_VALUES = (1, 1, 2, 2, 3, 3, 4, 4, 5, 5)
HP_FLAT_VALUES = (50, 200, 350, 500, 700, 950, 1200, 1500, 1900, 2400)
CRIT_VALUES = (0.30, 0.40, 0.50, 0.60, 0.75, 0.90, 1.00, 1.20, 1.40, 1.60)
EVADE_VALUES = (0.30, 0.40, 0.50, 0.60, 0.75, 0.90, 1.00, 1.20, 1.40, 1.60)
DR_VALUES = (0.25, 0.35, 0.45, 0.55, 0.65, 0.80, 0.90, 1.10, 1.30, 1.50)
HP_PCT_VALUES = (0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75)
GOLD_PCT_VALUES = (1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5)
GOLD_INSTANT = (5000, 15000, 25000, 36000, 47000, 58000, 69000, 80000, 90000, 100000)
DUST_INSTANT = (100, 140, 180, 220, 280, 340, 400, 450, 500, 600)
STONE_INSTANT = (1, 1, 2, 2, 3, 3, 4, 5, 6, 8)
ATTACK_FLAT_VALUES = (8, 10, 13, 16, 20, 25, 30, 36, 42, 50)
REGEN_VALUES = (1, 1, 2, 2, 3, 3, 4, 4, 5, 5)
FAMILY_PCT_VALUES = (2, 2, 3, 3, 4, 4, 5, 6, 7, 8)
MEDIA_PCT_VALUES = (3, 3, 4, 4, 5, 5, 6, 7, 8, 10)

MONSTER_FAMILIES: tuple[tuple[str, str], ...] = (
    ("beast", "зверям"),
    ("construct", "конструктам"),
    ("demon", "демонам"),
    ("dragon", "драконам"),
    ("elemental", "элементалям"),
    ("fae", "феям"),
    ("humanoid", "гуманоидам"),
    ("slime", "слизям"),
    ("undead", "нежити"),
)

MEDIA_TYPES: tuple[tuple[str, str, str], ...] = (
    ("media_dmg_text", "media_damage_text_percent", "Урон от текста"),
    ("media_dmg_sticker", "media_damage_sticker_percent", "Урон от стикеров"),
    ("media_dmg_photo", "media_damage_photo_percent", "Урон от фото"),
    ("media_dmg_gif", "media_damage_gif_percent", "Урон от GIF"),
    ("media_dmg_audio", "media_damage_audio_percent", "Урон от аудио"),
    ("media_dmg_voice", "media_damage_voice_percent", "Урон от голосовых"),
    ("media_dmg_video", "media_damage_video_percent", "Урон от видео"),
    ("media_dmg_link", "media_damage_link_percent", "Урон от ссылок"),
)


def _family_bonuses() -> tuple[PerfectionBonusDef, ...]:
    out: list[PerfectionBonusDef] = []
    for fam, ru in MONSTER_FAMILIES:
        out.append(
            PerfectionBonusDef(
                f"dmg_vs_{fam}",
                f"Урон по {ru}",
                "permanent",
                "situational",
                FAMILY_PCT_VALUES,
                unit="combat_pct",
                combat_key=f"damage_vs_monster_type_percent:{fam}",
            )
        )
    return tuple(out)


def _media_bonuses() -> tuple[PerfectionBonusDef, ...]:
    return tuple(
        PerfectionBonusDef(
            bid,
            title,
            "permanent",
            "situational",
            MEDIA_PCT_VALUES,
            unit="combat_pct",
            combat_key=ckey,
        )
        for bid, ckey, title in MEDIA_TYPES
    )


PERFECTION_BONUSES: tuple[PerfectionBonusDef, ...] = (
    PerfectionBonusDef("str_flat", "+СИЛ", "permanent", "primary", PRIMARY_VALUES),
    PerfectionBonusDef("agi_flat", "+ЛОВ", "permanent", "primary", PRIMARY_VALUES),
    PerfectionBonusDef("int_flat", "+ИНТ", "permanent", "primary", PRIMARY_VALUES),
    PerfectionBonusDef("end_flat", "+ВНС", "permanent", "primary", PRIMARY_VALUES),
    PerfectionBonusDef("chm_flat", "+ОБА", "permanent", "primary", PRIMARY_VALUES),
    PerfectionBonusDef("lck_flat", "+УДЧ", "permanent", "primary", PRIMARY_VALUES),
    PerfectionBonusDef("hp_flat", "+HP", "permanent", "hp", HP_FLAT_VALUES, unit="HP"),
    PerfectionBonusDef(
        "crit_chance_pct", "Крит", "permanent", "secondary", CRIT_VALUES, unit="%"
    ),
    PerfectionBonusDef(
        "evade_pct", "Уклонение", "permanent", "secondary", EVADE_VALUES, unit="%"
    ),
    PerfectionBonusDef(
        "dmg_reduce_pct", "Снижение урона", "permanent", "secondary", DR_VALUES, unit="%"
    ),
    PerfectionBonusDef(
        "hp_max_pct", "Макс. HP", "permanent", "secondary", HP_PCT_VALUES, unit="%"
    ),
    PerfectionBonusDef(
        "gold_bonus_pct", "Золото с дропа", "permanent", "secondary", GOLD_PCT_VALUES, unit="%"
    ),
    PerfectionBonusDef(
        "melee_damage_flat",
        "Урон ближнего",
        "permanent",
        "combat_dmg",
        ATTACK_FLAT_VALUES,
        combat_key="melee_damage_flat",
    ),
    PerfectionBonusDef(
        "ranged_damage_flat",
        "Урон дальнего",
        "permanent",
        "combat_dmg",
        ATTACK_FLAT_VALUES,
        combat_key="ranged_damage_flat",
    ),
    PerfectionBonusDef(
        "magic_damage_flat",
        "Урон магии",
        "permanent",
        "combat_dmg",
        ATTACK_FLAT_VALUES,
        combat_key="magic_damage_flat",
    ),
    PerfectionBonusDef(
        "hp_regen_per_min",
        "Реген HP",
        "permanent",
        "secondary",
        REGEN_VALUES,
        unit="HP/мин",
    ),
    *_family_bonuses(),
    *_media_bonuses(),
    PerfectionBonusDef(
        "gold_instant", "Золото", "instant", "resource", GOLD_INSTANT, unit="золото"
    ),
    PerfectionBonusDef(
        "dust_instant", "Пыль заточки", "instant", "resource", DUST_INSTANT, unit="пыль"
    ),
    PerfectionBonusDef(
        "stone_instant", "Камни защиты", "instant", "resource", STONE_INSTANT, unit="камни"
    ),
)

BONUS_BY_ID: dict[str, PerfectionBonusDef] = {b.id: b for b in PERFECTION_BONUSES}

WEIGHT_BY_CLASS_EARLY: dict[WeightClass, int] = {
    "resource": 18,
    "primary": 28,
    "hp": 12,
    "secondary": 14,
    "combat_dmg": 16,
    "situational": 12,
}
WEIGHT_BY_CLASS_LATE: dict[WeightClass, int] = {
    "resource": 14,
    "primary": 26,
    "hp": 10,
    "secondary": 16,
    "combat_dmg": 16,
    "situational": 18,
}

DUPLICATE_SOFTEN_AFTER = 3
DUPLICATE_SOFTEN_MULT = 0.5

SKILL_POINT_BONUS_ID = "skill_point_plus_1"
SKILL_POINT_TITLE_RU = "+1 очко навыка (ОПГ)"


def tier_index_for_level(perfection_level: int) -> int:
    """0-based tier index (T1=0 … T10=9), clamp выше 100 к T10."""
    lvl = max(1, int(perfection_level or 1))
    return min(TIER_COUNT - 1, (lvl - 1) // 10)


def tier_number_for_level(perfection_level: int) -> int:
    return tier_index_for_level(perfection_level) + 1


def value_for_bonus(bonus_id: str, perfection_level: int) -> float:
    bdef = BONUS_BY_ID[bonus_id]
    idx = tier_index_for_level(perfection_level)
    return float(bdef.values_by_tier[idx])


def stored_value_for_bonus(bonus_id: str, perfection_level: int) -> float:
    """Значение для записи в БД / агрегаты.

    unit \"%\": fraction (0.003 = 0.30%).
    unit \"combat_pct\": целые процентные пункты для damage pool.
    Остальное — как в каталоге.
    """
    raw = value_for_bonus(bonus_id, perfection_level)
    bdef = BONUS_BY_ID[bonus_id]
    if bdef.unit == "%":
        return raw / 100.0
    if bdef.unit == "combat_pct":
        return float(int(round(raw)))
    return raw


def combat_key_for_bonus(bonus_id: str) -> str | None:
    bdef = BONUS_BY_ID.get(bonus_id)
    if not bdef:
        return None
    if bdef.combat_key:
        return bdef.combat_key
    if bonus_id in (
        "melee_damage_flat",
        "ranged_damage_flat",
        "magic_damage_flat",
    ):
        return bonus_id
    return None


def weight_table_for_tier(tier_index: int) -> dict[WeightClass, int]:
    if tier_index <= 2:
        return WEIGHT_BY_CLASS_EARLY
    return WEIGHT_BY_CLASS_LATE


def format_offer_value(bonus_id: str, perfection_level: int) -> str:
    """Человекочитаемое значение для карточки оффера."""
    if bonus_id == SKILL_POINT_BONUS_ID:
        return "+1"
    bdef = BONUS_BY_ID[bonus_id]
    raw = value_for_bonus(bonus_id, perfection_level)
    if bdef.unit in ("%", "combat_pct"):
        return f"+{raw:g}%"
    if bdef.unit == "HP":
        return f"+{int(raw)} HP"
    if bdef.unit == "HP/мин":
        return f"+{int(raw)} HP/мин"
    if raw == int(raw):
        return f"+{int(raw)}"
    return f"+{raw:g}"
