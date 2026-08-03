"""Каталог бонусов системы Совершенствования (post-60)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

WeightClass = Literal["resource", "primary", "hp", "secondary", "combat_dmg", "situational"]
BonusKind = Literal["permanent", "instant"]
# unit:
#   "" | "HP" | "золото" | "пыль" | "камни" — абсолютные
#   "%" — secondary fraction в бою (store = raw/100)
#   "%_regen" — доля от натурального регена 5+max(0,END-10) (store = raw/100)
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

# Калибровка под L60 Mid (~400–800 статов) и High/IceFear (~3000–6000+).
# Цель: заметный pick на High без late-tier взрыва; лестницы монотонны, сосед ≤~1.6×.
PRIMARY_VALUES = (20, 32, 50, 70, 95, 130, 175, 230, 300, 400)
HP_FLAT_VALUES = (300, 480, 750, 1200, 1800, 2600, 3600, 5000, 7000, 9500)
CRIT_VALUES = (0.70, 0.90, 1.15, 1.40, 1.70, 2.00, 2.35, 2.70, 3.10, 3.50)
EVADE_VALUES = (0.70, 0.90, 1.15, 1.40, 1.70, 2.00, 2.35, 2.70, 3.10, 3.50)
DR_VALUES = (0.55, 0.75, 1.00, 1.25, 1.55, 1.85, 2.20, 2.55, 2.90, 3.25)
HP_PCT_VALUES = (1.0, 1.3, 1.7, 2.1, 2.6, 3.1, 3.5, 3.9, 4.3, 4.8)
GOLD_PCT_VALUES = (1.5, 2.0, 2.6, 3.2, 3.9, 4.6, 5.2, 5.8, 6.4, 7.0)
GOLD_INSTANT = (10000, 15000, 23000, 35000, 50000, 75000, 110000, 150000, 200000, 275000)
DUST_INSTANT = (150, 220, 320, 450, 620, 850, 1150, 1500, 1900, 2400)
STONE_INSTANT = (1, 2, 3, 4, 5, 6, 8, 10, 12, 15)
# Attack flats: ~1–3% High mid; T10 capped so один pick не ~15% пула
ATTACK_FLAT_VALUES = (40, 60, 90, 120, 155, 200, 250, 310, 380, 450)
# % от натурального регена (5 + max(0, END-10)); store = raw/100
REGEN_VALUES = (2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 7.5, 9.0, 11.0)
FAMILY_PCT_VALUES = (3, 4, 5, 6, 7, 8, 9, 10, 11, 12)
MEDIA_PCT_VALUES = (3, 4, 5, 6, 7, 8, 9, 10, 11, 12)

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
    PerfectionBonusDef("end_flat", "+ВЫН", "permanent", "primary", PRIMARY_VALUES),
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
        "Реген HP (% от базы)",
        "permanent",
        "secondary",
        REGEN_VALUES,
        unit="%_regen",
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
    "situational": 10,  # меньше early clutter после ребаланса
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

    unit \"%\" / \"%_regen\": fraction (0.03 = 3%).
    unit \"combat_pct\": целые процентные пункты для damage pool.
    Остальное — как в каталоге.
    """
    raw = value_for_bonus(bonus_id, perfection_level)
    bdef = BONUS_BY_ID[bonus_id]
    if bdef.unit in ("%", "%_regen"):
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


def _format_int_grouped(n: int) -> str:
    """1234567 → '1 234 567' (thin space thousands)."""
    s = f"{int(n):,}".replace(",", "\u202f")
    return s


def format_offer_value(bonus_id: str, perfection_level: int) -> str:
    """Человекочитаемое значение для карточки оффера."""
    if bonus_id == SKILL_POINT_BONUS_ID:
        return "+1"
    bdef = BONUS_BY_ID[bonus_id]
    raw = value_for_bonus(bonus_id, perfection_level)
    if bdef.unit == "%_regen":
        return f"+{raw:g}% регена"
    if bdef.unit in ("%", "combat_pct"):
        return f"+{raw:g}%"
    if bdef.unit == "HP":
        return f"+{_format_int_grouped(int(raw))} HP"
    if bdef.unit == "золото":
        return f"+{_format_int_grouped(int(raw))} золота"
    if bdef.unit == "пыль":
        return f"+{_format_int_grouped(int(raw))} пыли"
    if bdef.unit == "камни":
        n = int(raw)
        return f"+{n} {_stone_word(n)}"
    if raw == int(raw):
        return f"+{int(raw)}"
    return f"+{raw:g}"


def _stone_word(n: int) -> str:
    n = abs(int(n)) % 100
    if 11 <= n <= 14:
        return "камней"
    n = n % 10
    if n == 1:
        return "камень"
    if 2 <= n <= 4:
        return "камня"
    return "камней"
