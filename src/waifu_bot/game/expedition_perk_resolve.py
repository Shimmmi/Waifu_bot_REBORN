"""Черновые id перков из ТЗ/БД → канонические id из expedition_data.PERKS."""

from __future__ import annotations

from typing import Iterable

from waifu_bot.game.expedition_data import PERK_BY_ID

# Черновой id (миграция 0026 / дизайн-док) → один или несколько реальных перков
DRAFT_EXPEDITION_PERK_TO_CANONICAL: dict[str, tuple[str, ...]] = {
    "magic_ward": ("magic_resistance", "mana_shield", "light_protection"),
    "spirit_ward": ("exorcist", "curse_removal", "priest"),
    "nature_weather": ("frostproof", "navigator", "wind_walker"),
    "def_fortress": ("mountain_engineer", "gas_mask", "magic_resistance"),
    "heal_antidote": ("chemist", "gas_filter", "mushroom_expert"),
    "nature_poison": ("mushroom_expert", "gas_mask", "swamp_walker"),
    "spirit_curse": ("curse_removal", "exorcist", "strong_spirit"),
    "spirit_anchor": ("strong_spirit", "mental_shield", "exorcist"),
    "stealth_shadow": ("scout", "spider_hunter", "mental_clarity"),
    "trap_detect": ("scout", "spider_hunter"),
    "know_history": ("archaeologist", "photographic_memory"),
    "know_language": ("photographic_memory", "archaeologist", "trusting"),
    "nature_pathfind": ("navigator", "desert_walker", "swamp_walker"),
    "social_charm": ("trusting", "optimist", "lucky"),
    "combat_strike": ("goblin_shaker", "orc_hunter", "elf_slayer"),
    "combat_tactics": ("orc_hunter", "troll_slayer", "goblin_shaker"),
    "spirit_drain": ("exorcist", "mana_shield", "priest"),
    "trap_disarm": ("scout", "mountain_engineer"),
    "spirit_commune": ("priest", "exorcist", "curse_removal"),
    "stealth_disguise": ("scout", "mental_clarity", "spider_hunter"),
    "social_bribe": ("trusting", "lucky", "optimist"),
    "magic_identify": ("magic_researcher", "anti_mage", "archaeologist"),
    "luck_finder": ("lucky",),
    "trade_fence": ("lucky", "trusting"),
}


def normalize_expedition_paired_perk_ids(raw: Iterable[str] | None) -> list[str]:
    """
    Приводит список id к каноническим перкам из PERKS.
    Известные черновые id заменяются на tuple из DRAFT_...; неизвестные отбрасываются.
    """
    seen: set[str] = set()
    out: list[str] = []
    for x in raw or []:
        pid = str(x).strip() if x else ""
        if not pid:
            continue
        if pid in PERK_BY_ID:
            if pid not in seen:
                seen.add(pid)
                out.append(pid)
            continue
        mapped = DRAFT_EXPEDITION_PERK_TO_CANONICAL.get(pid)
        if mapped:
            for c in mapped:
                if c in PERK_BY_ID and c not in seen:
                    seen.add(c)
                    out.append(c)
    return out
