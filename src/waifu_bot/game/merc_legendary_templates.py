"""Fixed Legendary mercenary templates (gacha icons)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LegendaryMercTemplate:
    id: str
    name_ru: str
    race: int
    class_: int
    legendary_perk_id: str
    lore_ru: str
    art_key: str = ""


# 18 starter templates — art_key optional stub
LEGENDARY_TEMPLATES: tuple[LegendaryMercTemplate, ...] = (
    LegendaryMercTemplate("leg_ashen_blade", "Пепельная Клинок", 6, 5, "leg_storm", "Демон-ассасин, чей клинок пьёт темп боя."),
    LegendaryMercTemplate("leg_ivory_aegis", "Белая Эгида", 4, 1, "leg_citadel", "Ангел-рыцарь, стена для всего отряда."),
    LegendaryMercTemplate("leg_moon_oracle", "Лунный Оракул", 2, 4, "leg_oracle", "Эльфийка-маг, читающая ритм арены."),
    LegendaryMercTemplate("leg_crimson_howl", "Алый Вой", 3, 2, "leg_storm", "Зверолюд-воин берсеркского пути."),
    LegendaryMercTemplate("leg_veil_sister", "Сестра Завесы", 5, 6, "leg_oracle", "Вампирша-лекарь с тёмным очищением."),
    LegendaryMercTemplate("leg_coin_witch", "Монетная Ведьма", 7, 7, "leg_oracle", "Фея-торговка, ломающая темп врага."),
    LegendaryMercTemplate("leg_storm_archer", "Грозовой Лук", 1, 3, "leg_storm", "Человек-лучник с пробивающим залпом."),
    LegendaryMercTemplate("leg_obsidian_wall", "Обсидиановая Стена", 6, 1, "leg_citadel", "Демон-рыцарь неприступной обороны."),
    LegendaryMercTemplate("leg_dawn_medic", "Медик Рассвета", 4, 6, "leg_oracle", "Ангел поддержки на грани контроля."),
    LegendaryMercTemplate("leg_night_duelist", "Ночной Дуэлянт", 5, 5, "leg_storm", "Вампир-ассасин первого удара."),
    LegendaryMercTemplate("leg_grove_warden", "Страж Рощи", 2, 2, "leg_citadel", "Эльф-воин живого барьера."),
    LegendaryMercTemplate("leg_sand_prophet", "Пророк Песков", 1, 4, "leg_oracle", "Человек-маг истощения и темпа."),
    LegendaryMercTemplate("leg_fang_ravager", "Клык Разорителя", 3, 5, "leg_storm", "Зверолюд с рваным натиском."),
    LegendaryMercTemplate("leg_glass_paladin", "Стеклянный Паладин", 7, 1, "leg_citadel", "Фея-рыцарь лёгкой, но жёсткой эгиды."),
    LegendaryMercTemplate("leg_blood_chaplain", "Кровавый Капеллан", 5, 6, "leg_oracle", "Вампир поддержки с меткой добычи."),
    LegendaryMercTemplate("leg_iron_tactician", "Железный Тактик", 1, 7, "leg_oracle", "Человек-торговец поля боя."),
    LegendaryMercTemplate("leg_sky_bulwark", "Небесный Бастион", 4, 2, "leg_citadel", "Ангел-воин щита и удара."),
    LegendaryMercTemplate("leg_ember_skirmish", "Угольный Застрельщик", 6, 3, "leg_storm", "Демон-лучник засады."),
)

TEMPLATE_BY_ID: dict[str, LegendaryMercTemplate] = {t.id: t for t in LEGENDARY_TEMPLATES}

DEBUT_PICK_IDS: tuple[str, ...] = (
    "leg_ashen_blade",
    "leg_ivory_aegis",
    "leg_moon_oracle",
)


def template_public(t: LegendaryMercTemplate, *, unlocked: bool = False) -> dict:
    return {
        "id": t.id,
        "name": t.name_ru if unlocked else "???",
        "race": t.race if unlocked else None,
        "class": t.class_ if unlocked else None,
        "legendary_perk_id": t.legendary_perk_id if unlocked else None,
        "lore": t.lore_ru if unlocked else "",
        "art_key": t.art_key,
        "unlocked": unlocked,
    }
