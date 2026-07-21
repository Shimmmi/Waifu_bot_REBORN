"""Perk types ATK/DEF/SUP and archetypes from perk type multisets."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable

PerkType = str  # "ATK" | "DEF" | "SUP"

STANCE_ASSAULT = "Assault"
STANCE_WARD = "Ward"
STANCE_TACTICS = "Tactics"

# Type RPS: ATK beats DEF, DEF beats SUP, SUP beats ATK
TYPE_BEATS: dict[str, str] = {
    "ATK": "DEF",
    "DEF": "SUP",
    "SUP": "ATK",
}

TYPE_EDGE = 0.20  # ± edge magnitude


@dataclass(frozen=True)
class ArchetypeDef:
    id: str
    name_ru: str
    stance: str
    bonus_ru: str


# 3-perk archetypes (canonical for Epic/Legendary)
ARCHETYPE_3: dict[tuple[str, ...], ArchetypeDef] = {
    ("ATK", "ATK", "ATK"): ArchetypeDef("berserker", "Берсерк", STANCE_ASSAULT, "+урон; −эффективность хила"),
    ("ATK", "ATK", "DEF"): ArchetypeDef("ravager", "Разоритель", STANCE_ASSAULT, "+пробитие"),
    ("ATK", "ATK", "SUP"): ArchetypeDef("duelist", "Дуэлянт", STANCE_ASSAULT, "+first-strike"),
    ("ATK", "DEF", "DEF"): ArchetypeDef("bulwark", "Бастион", STANCE_WARD, "+DR; taunt"),
    ("ATK", "DEF", "SUP"): ArchetypeDef("tactician", "Тактик", STANCE_TACTICS, "гибкий edge"),
    ("ATK", "SUP", "SUP"): ArchetypeDef("chaplain", "Капеллан", STANCE_TACTICS, "heal/mark"),
    ("DEF", "DEF", "DEF"): ArchetypeDef("citadel", "Цитадель", STANCE_WARD, "max DR; −свой урон"),
    ("DEF", "DEF", "SUP"): ArchetypeDef("paladin", "Паладин", STANCE_WARD, "DR + cleanse"),
    ("DEF", "SUP", "SUP"): ArchetypeDef("medic", "Медик", STANCE_TACTICS, "heal-pulse"),
    ("SUP", "SUP", "SUP"): ArchetypeDef("oracle", "Оракул", STANCE_TACTICS, "tempo/control"),
}

ARCHETYPE_2: dict[tuple[str, ...], ArchetypeDef] = {
    ("ATK", "ATK"): ArchetypeDef("vanguard", "Натиск", STANCE_ASSAULT, "+pressure"),
    ("ATK", "DEF"): ArchetypeDef("gladiator", "Гладиатор", STANCE_ASSAULT, "ATK/DEF mix"),
    ("ATK", "SUP"): ArchetypeDef("skirmisher", "Застрельщик", STANCE_ASSAULT, "skirmish"),
    ("DEF", "DEF"): ArchetypeDef("shieldbearer", "Щитоносец", STANCE_WARD, "+barrier"),
    ("DEF", "SUP"): ArchetypeDef("warden", "Страж", STANCE_WARD, "guard+support"),
    ("SUP", "SUP"): ArchetypeDef("catalyst", "Катализатор", STANCE_TACTICS, "+tempo"),
}

ARCHETYPE_1: dict[tuple[str, ...], ArchetypeDef] = {
    ("ATK",): ArchetypeDef("fighter", "Боец", STANCE_ASSAULT, "базовая атака"),
    ("DEF",): ArchetypeDef("defender", "Защитник", STANCE_WARD, "базовая защита"),
    ("SUP",): ArchetypeDef("channel", "Канал", STANCE_TACTICS, "базовая поддержка"),
}


def _norm_key(types: Iterable[str]) -> tuple[str, ...]:
    order = {"ATK": 0, "DEF": 1, "SUP": 2}
    cleaned = [t for t in types if t in order]
    return tuple(sorted(cleaned, key=lambda t: order[t]))


def resolve_archetype(perk_types: list[str]) -> ArchetypeDef:
    key = _norm_key(perk_types)
    if len(key) >= 3:
        # take first 3 after sort for Epic/Leg with 3 slots
        k3 = key[:3] if len(key) == 3 else _norm_key(list(Counter(key).elements())[:3])
        # rebuild proper multiset of exactly 3
        c = Counter(key)
        built: list[str] = []
        for t in ("ATK", "DEF", "SUP"):
            built.extend([t] * c[t])
        built = built[:3]
        while len(built) < 3:
            built.append("ATK")
        k3 = _norm_key(built)
        if k3 in ARCHETYPE_3:
            return ARCHETYPE_3[k3]
    if len(key) == 2 and key in ARCHETYPE_2:
        return ARCHETYPE_2[key]
    if len(key) == 1 and key in ARCHETYPE_1:
        return ARCHETYPE_1[key]
    if not key:
        return ArchetypeDef("fighter", "Боец", STANCE_ASSAULT, "базовая атака")
    # fallback by majority
    c = Counter(key)
    maj = c.most_common(1)[0][0]
    return ARCHETYPE_1[(maj,)]


def stance_edge(attacker_stance: str, defender_stance: str) -> float:
    """Return edge for attacker vs defender stance (−TYPE_EDGE..+TYPE_EDGE)."""
    beats = {
        STANCE_ASSAULT: STANCE_WARD,
        STANCE_WARD: STANCE_TACTICS,
        STANCE_TACTICS: STANCE_ASSAULT,
    }
    if attacker_stance == defender_stance:
        return 0.0
    if beats.get(attacker_stance) == defender_stance:
        return TYPE_EDGE
    if beats.get(defender_stance) == attacker_stance:
        return -TYPE_EDGE
    return 0.0


def type_edge(atk_type: str, def_type: str) -> float:
    if atk_type == def_type:
        return 0.0
    if TYPE_BEATS.get(atk_type) == def_type:
        return TYPE_EDGE
    if TYPE_BEATS.get(def_type) == atk_type:
        return -TYPE_EDGE
    return 0.0
