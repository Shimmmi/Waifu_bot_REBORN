"""Базовые характеристики ОВ: стартовые значения и плоские бонусы расы/класса (единый источник для API и логики)."""

from __future__ import annotations

from typing import Any

from waifu_bot.db.models.waifu import WaifuClass, WaifuRace

MAIN_WAIFU_BASE_STATS: dict[str, int] = {
    "strength": 10,
    "agility": 10,
    "intelligence": 10,
    "endurance": 10,
    "charm": 10,
    "luck": 10,
}

MAIN_WAIFU_RACE_FLAT_BONUSES: dict[int, dict[str, int]] = {
    int(WaifuRace.HUMAN): {},
    int(WaifuRace.ELF): {"agility": 2, "intelligence": 2, "luck": 1},
    int(WaifuRace.BEASTKIN): {"strength": 2, "agility": 2, "endurance": 1},
    int(WaifuRace.ANGEL): {"charm": 2, "intelligence": 1, "luck": 1},
    int(WaifuRace.VAMPIRE): {"strength": 1, "endurance": 2, "charm": 1, "luck": 1},
    int(WaifuRace.DEMON): {"strength": 2, "intelligence": 1, "luck": 1},
    int(WaifuRace.FAIRY): {"agility": 2, "charm": 2, "luck": 2},
}

MAIN_WAIFU_CLASS_FLAT_BONUSES: dict[int, dict[str, int]] = {
    int(WaifuClass.KNIGHT): {"strength": 2, "endurance": 2},
    int(WaifuClass.WARRIOR): {"strength": 2, "agility": 1, "endurance": 1},
    int(WaifuClass.ARCHER): {"agility": 3, "luck": 1},
    int(WaifuClass.MAGE): {"intelligence": 3, "luck": 1},
    int(WaifuClass.ASSASSIN): {"agility": 2, "strength": 1, "luck": 1},
    int(WaifuClass.HEALER): {"intelligence": 2, "charm": 2},
    int(WaifuClass.MERCHANT): {"charm": 2, "luck": 2},
}

_STAT_KEYS = frozenset(MAIN_WAIFU_BASE_STATS.keys())


def race_flat_bonuses_for(race: int | WaifuRace) -> dict[str, int]:
    rid = int(race)
    return dict(MAIN_WAIFU_RACE_FLAT_BONUSES.get(rid, {}))


def class_flat_bonuses_for(class_: int | WaifuClass) -> dict[str, int]:
    cid = int(class_)
    return dict(MAIN_WAIFU_CLASS_FLAT_BONUSES.get(cid, {}))


def compute_main_waifu_base_stats(race: WaifuRace | int, class_: WaifuClass | int) -> dict[str, int]:
    """Сумма базы + раса + класс (как при создании ОВ)."""
    stats = MAIN_WAIFU_BASE_STATS.copy()
    r = int(race)
    c = int(class_)
    for key, bonus in MAIN_WAIFU_RACE_FLAT_BONUSES.get(r, {}).items():
        stats[key] = stats.get(key, 0) + bonus
    for key, bonus in MAIN_WAIFU_CLASS_FLAT_BONUSES.get(c, {}).items():
        stats[key] = stats.get(key, 0) + bonus
    return stats


def validate_bonus_dict_keys(bonus_map: dict[Any, Any], *, context: str) -> None:
    """Для тестов и отладки: ключи только из шести основных статов."""
    for k in bonus_map:
        ks = str(k)
        if ks not in _STAT_KEYS:
            raise ValueError(f"{context}: invalid stat key {k!r}")
