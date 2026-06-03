"""Человекочитаемые подписи для effect_key аффиксов (UI / названия в характеристиках)."""

from __future__ import annotations

# Ключи в нижнем регистре
_MONSTER_FAMILY_RU: dict[str, str] = {
    "beast": "зверей",
    "construct": "конструктов",
    "demon": "демонов",
    "dragon": "драконов",
    "elemental": "элементалей",
    "fae": "фей",
    "humanoid": "гуманоидов",
    "slime": "слизней",
    "undead": "нежити",
}

_EFFECT_STAT_DESCRIPTION_RU: dict[str, str] = {
    # Основные статы (аффиксы)
    "strength": "Бонус к силе",
    "agility": "Бонус к ловкости",
    "intelligence": "Бонус к интеллекту",
    "endurance": "Бонус к выносливости",
    "charm": "Бонус к обаянию",
    "luck": "Бонус к удаче",
    # Урон / защита
    "damage_flat": "Доп. урон к оружию",
    "damage_percent": "Доп. урон к оружию %",
    "melee_damage_flat": "Урон в ближнем бою",
    "ranged_damage_flat": "Урон в дальнем бою",
    "magic_damage_flat": "Урон магией",
    "defense_flat": "Бонус к защите",
    "defense_percent": "Защита %",
    "hp_flat": "Доп. HP",
    "hp_percent": "HP %",
    "crit_chance_flat": "Шанс крита",
    "crit_chance_percent": "Шанс крита",
    "merchant_discount_flat": "Скидка у торговца",
    "merchant_discount_percent": "Скидка у торговца",
    "sell_price_bonus_percent": "Бонус к цене скупки",
    "tavern_discount_percent": "Скидка в таверне",
    # Вторички (аффиксы *_pct — в сотых долях процента в значении)
    "crit_chance_pct": "Шанс крита",
    "evade_pct": "Уклонение",
    "dmg_reduce_pct": "Снижение урона",
    "hp_max_pct": "Запас HP",
    "exp_bonus_pct": "Бонус к опыту",
    "gold_bonus_pct": "Доп. золото",
    "magic_find_pct": "Поиск магических предметов",
    # Медиа-урон
    "media_damage_text_percent": "Урон от текста",
    "media_damage_sticker_percent": "Урон от стикеров",
    "media_damage_photo_percent": "Урон от фото",
    "media_damage_gif_percent": "Урон от GIF",
    "media_damage_audio_percent": "Урон от аудио",
    "media_damage_voice_percent": "Урон от голосовых",
    "media_damage_video_percent": "Урон от видео",
    "media_damage_link_percent": "Урон от ссылок",
}


def effect_stat_description_ru(effect_key: str) -> str:
    """Краткая подпись строки характеристики (без сырого ключа)."""
    raw = str(effect_key or "").strip()
    low = raw.lower().replace("audioo", "audio").replace("magii", "magic")
    if low in _EFFECT_STAT_DESCRIPTION_RU:
        return _EFFECT_STAT_DESCRIPTION_RU[low]
    if low.startswith("damage_vs_monster_type_flat:"):
        fam = low.split(":", 1)[1].strip().lower()
        ru = _MONSTER_FAMILY_RU.get(fam, fam)
        return f"Урон по {ru}"
    if low.startswith("damage_vs_monster_type_percent:"):
        fam = low.split(":", 1)[1].strip().lower()
        ru = _MONSTER_FAMILY_RU.get(fam, fam)
        return f"Урон % по {ru}"
    _BR_RU = {"warrior": "воина", "shadow": "тени", "sage": "мудреца"}
    if low.startswith("passive_node_level_add:"):
        return ""
    if low.startswith("passive_branch_level_add:"):
        br = low.split(":", 1)[1].strip().lower()
        ru = _BR_RU.get(br, br)
        return f"+ур. ко всем изученным навыкам ветки ({ru})"
    if low == "passive_all_nodes_level_add":
        return "+ур. ко всем изученным пассивным навыкам"
    return raw or "Свойство"


_PRIMARY_STATS = frozenset(
    {"strength", "agility", "intelligence", "endurance", "charm", "luck"}
)

BONUS_CATEGORY_LABELS: dict[str, str] = {
    "stats": "Основные статы",
    "damage": "Урон и крит",
    "defense": "Защита и выживаемость",
    "economy": "Золото, опыт, торговля",
    "skills": "Навыки / пассивы",
    "monster": "Урон по типам монстров",
    "media": "Урон от медиа",
    "other": "Прочее",
}

BONUS_CATEGORY_ORDER: tuple[str, ...] = (
    "stats",
    "damage",
    "defense",
    "economy",
    "skills",
    "monster",
    "media",
    "other",
)


def _normalize_effect_key(effect_key: str) -> str:
    return (
        str(effect_key or "")
        .strip()
        .lower()
        .replace("audioo", "audio")
        .replace("magii", "magic")
    )


def effect_bonus_category(effect_key: str) -> tuple[str, str]:
    """Обобщённая категория бонуса для фильтров UI (id, подпись ru)."""
    low = _normalize_effect_key(effect_key)
    if not low:
        return "other", BONUS_CATEGORY_LABELS["other"]
    if low in _PRIMARY_STATS:
        return "stats", BONUS_CATEGORY_LABELS["stats"]
    if low.startswith("passive_"):
        return "skills", BONUS_CATEGORY_LABELS["skills"]
    if low.startswith("damage_vs_monster_type_"):
        return "monster", BONUS_CATEGORY_LABELS["monster"]
    if low.startswith("media_damage_"):
        return "media", BONUS_CATEGORY_LABELS["media"]
    if (
        low.startswith("gold_")
        or low.startswith("exp_")
        or low.startswith("merchant_")
        or low.startswith("sell_price_")
        or low.startswith("tavern_")
        or low == "magic_find_pct"
    ):
        return "economy", BONUS_CATEGORY_LABELS["economy"]
    if (
        low.startswith("damage_")
        or low.startswith("melee_")
        or low.startswith("ranged_")
        or low.startswith("magic_")
        or low.startswith("crit_")
    ):
        return "damage", BONUS_CATEGORY_LABELS["damage"]
    if (
        low.startswith("defense_")
        or low.startswith("hp_")
        or low in ("dmg_reduce_pct", "evade_pct", "hp_max_pct")
    ):
        return "defense", BONUS_CATEGORY_LABELS["defense"]
    return "other", BONUS_CATEGORY_LABELS["other"]
