"""Merc perk catalog v2 — universal Ops+Arena (replaces creature-specific expedition perks)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from waifu_bot.db.models.waifu import WaifuRarity
from waifu_bot.game.merc_archetypes import PerkType, resolve_archetype
from waifu_bot.game.merc_threat_tags import TAG_RESIST_CAP


@dataclass(frozen=True)
class MercPerk:
    id: str
    name_ru: str
    perk_type: PerkType  # ATK / DEF / SUP
    rarity: int  # 1..5
    tags: tuple[str, ...]
    power_pct: float  # coverage strength at full
    flavor_ru: str = ""


# Ladder families: Common→Legendary variants share prefix semantics
PERKS: list[MercPerk] = [
    # --- ATK ---
    MercPerk("cleave_c", "Рассечение", "ATK", 1, ("pressure",), 0.12, "Широкий удар"),
    MercPerk("cleave_u", "Рассечение+", "ATK", 2, ("pressure", "focus_fire"), 0.18),
    MercPerk("first_strike_c", "Первый удар", "ATK", 1, ("ambush",), 0.12),
    MercPerk("first_strike_u", "Первый удар+", "ATK", 2, ("ambush", "tempo"), 0.18),
    MercPerk("first_strike_r", "Импульс атаки", "ATK", 3, ("ambush", "burst"), 0.24),
    MercPerk("execute_r", "Добивание", "ATK", 3, ("burst", "focus_fire"), 0.24),
    MercPerk("execute_e", "Казнь", "ATK", 4, ("burst", "focus_fire"), 0.32),
    MercPerk("pierce_u", "Пробитие", "ATK", 2, ("pierce",), 0.18),
    MercPerk("pierce_r", "Иглобой", "ATK", 3, ("pierce", "pressure"), 0.24),
    MercPerk("rend_r", "Рваная рана", "ATK", 3, ("antiheal", "attrition"), 0.24),
    MercPerk("berserk_e", "Ярость", "ATK", 4, ("pressure", "burst"), 0.32),
    MercPerk("ambush_e", "Тень клинка", "ATK", 4, ("ambush", "pierce", "tempo"), 0.32),
    MercPerk("leg_storm", "Буря клинков", "ATK", 5, ("pressure", "burst", "focus_fire"), 0.40),
    # --- DEF ---
    MercPerk("ironwall_c", "Железная стена", "DEF", 1, ("barrier",), 0.12),
    MercPerk("ironwall_u", "Железная стена+", "DEF", 2, ("barrier", "sustain"), 0.18),
    MercPerk("fortify_c", "Укрепление", "DEF", 1, ("sustain",), 0.12),
    MercPerk("fortify_r", "Бастион плоти", "DEF", 3, ("sustain", "barrier"), 0.24),
    MercPerk("aegis_u", "Эгида", "DEF", 2, ("barrier",), 0.18),
    MercPerk("aegis_e", "Святая эгида", "DEF", 4, ("barrier", "cleanse_need"), 0.32),
    MercPerk("taunt_r", "Провокация", "DEF", 3, ("pressure", "focus_fire"), 0.24),
    MercPerk("resilience_u", "Стойкость", "DEF", 2, ("attrition", "sustain"), 0.18),
    MercPerk("anti_crit_r", "Несокрушимость", "DEF", 3, ("burst",), 0.24),
    MercPerk("brace_e", "Контрудар щита", "DEF", 4, ("barrier", "pierce"), 0.32),
    MercPerk("leg_citadel", "Неприступная цитадель", "DEF", 5, ("barrier", "sustain", "attrition"), 0.40),
    # --- SUP ---
    MercPerk("mend_c", "Исцеление", "SUP", 1, ("sustain",), 0.12),
    MercPerk("mend_u", "Исцеление+", "SUP", 2, ("sustain", "cleanse_need"), 0.18),
    MercPerk("cleanse_r", "Очищение", "SUP", 3, ("cleanse_need", "control"), 0.24),
    MercPerk("mark_u", "Метка добычи", "SUP", 2, ("focus_fire",), 0.18),
    MercPerk("mark_r", "Метка смерти", "SUP", 3, ("focus_fire", "tempo"), 0.24),
    MercPerk("haste_r", "Ускорение", "SUP", 3, ("tempo", "ambush"), 0.24),
    MercPerk("barrier_share_e", "Общий барьер", "SUP", 4, ("barrier", "sustain"), 0.32),
    MercPerk("insight_u", "Проницательность", "SUP", 2, ("control",), 0.18),
    MercPerk("insight_e", "Ясный разум", "SUP", 4, ("control", "cleanse_need"), 0.32),
    MercPerk("rally_e", "Призыв к бою", "SUP", 4, ("pressure", "tempo"), 0.32),
    MercPerk("suppress_r", "Подавление", "SUP", 3, ("control", "antiheal"), 0.24),
    MercPerk("leg_oracle", "Оракул войны", "SUP", 5, ("tempo", "control", "cleanse_need"), 0.40),
]

PERK_BY_ID: dict[str, MercPerk] = {p.id: p for p in PERKS}

# Legacy expedition perk id → new merc perk id (best-effort)
LEGACY_PERK_MAP: dict[str, str] = {
    "gas_mask": "resilience_u",
    "diver": "fortify_c",
    "fireproof": "ironwall_c",
    "frostproof": "ironwall_c",
    "navigator": "insight_u",
    "desert_walker": "resilience_u",
    "gas_filter": "resilience_u",
    "snow_warrior": "fortify_r",
    "acid_proof": "aegis_u",
    "wind_walker": "haste_r",
    "elf_slayer": "pierce_u",
    "orc_hunter": "cleave_u",
    "priest": "mend_u",
    "demon_slayer": "execute_r",
    "dragonslayer": "pierce_r",
    "goblin_shaker": "cleave_c",
    "troll_slayer": "rend_r",
    "vampire_hunter": "anti_crit_r",
    "entomologist": "mark_u",
    "bat_hunter": "first_strike_c",
    "mushroom_expert": "cleanse_r",
    "scout": "first_strike_u",
    "archaeologist": "insight_u",
    "spider_hunter": "ambush_e",
    "chemist": "suppress_r",
    "magic_researcher": "insight_e",
    "exorcist": "cleanse_r",
    "mountain_engineer": "brace_e",
    "anti_magnet": "aegis_u",
    "curse_removal": "cleanse_r",
    "anti_mage": "suppress_r",
    "spatial_mage": "haste_r",
    "light_protection": "aegis_e",
    "magic_resistance": "ironwall_u",
    "chronomancer": "haste_r",
    "accelerator": "first_strike_r",
    "spatial_navigator": "insight_u",
    "mana_shield": "barrier_share_e",
    "lucky": "mark_r",
    "mental_shield": "insight_e",
    "strong_spirit": "fortify_r",
    "mental_clarity": "insight_u",
    "sleepless": "resilience_u",
    "trusting": "rally_e",
    "photographic_memory": "mark_u",
    "calm": "mend_c",
    "optimist": "mend_u",
    "anger_control": "brace_e",
    "passionate": "berserk_e",
}

# Slots by hired rarity
PERK_SLOTS_BY_RARITY: dict[int, int] = {
    int(WaifuRarity.COMMON): 1,
    int(WaifuRarity.UNCOMMON): 2,
    int(WaifuRarity.RARE): 2,
    int(WaifuRarity.EPIC): 3,
    int(WaifuRarity.LEGENDARY): 3,
}


def map_legacy_perk_id(old_id: str) -> str:
    oid = str(old_id or "").strip()
    if oid in PERK_BY_ID:
        return oid
    return LEGACY_PERK_MAP.get(oid, "cleave_c")


def migrate_perk_list(perks: list | None) -> list[str]:
    out: list[str] = []
    for p in perks or []:
        nid = map_legacy_perk_id(p if isinstance(p, str) else str(p))
        if nid not in out:
            out.append(nid)
    return out


def perk_types_for(perk_ids: Iterable[str]) -> list[str]:
    types: list[str] = []
    for pid in perk_ids:
        perk = PERK_BY_ID.get(pid)
        if perk:
            types.append(perk.perk_type)
    return types


def archetype_for_perks(perk_ids: list[str]):
    return resolve_archetype(perk_types_for(perk_ids))


def tag_coverage(perk_ids: list[str], *, perk_levels: dict | None = None) -> dict[str, float]:
    """Return tag → resist fraction (capped)."""
    levels = perk_levels or {}
    raw: dict[str, float] = {}
    for i, pid in enumerate(perk_ids):
        perk = PERK_BY_ID.get(pid)
        if not perk:
            continue
        lvl = max(1, int(levels.get(pid, levels.get(str(pid), 1)) or 1))
        mult = 1.0 + 0.04 * (lvl - 1)
        strength = perk.power_pct * mult
        tags = list(perk.tags)
        # Legendary 3rd tag at 70% efficiency
        for ti, tag in enumerate(tags):
            eff = strength if ti < 2 else strength * 0.70
            raw[tag] = raw.get(tag, 0.0) + eff
    return {t: min(TAG_RESIST_CAP, v) for t, v in raw.items()}


def perks_allowed_for_hired_rarity(hired_rarity: int) -> list[MercPerk]:
    r = int(hired_rarity)
    return [p for p in PERKS if p.rarity <= r]


def roll_perk_ids_for_rarity(hired_rarity: int, *, rng=None, forced_legendary_id: str | None = None) -> list[str]:
    import random

    rnd = rng or random
    slots = PERK_SLOTS_BY_RARITY.get(int(hired_rarity), 1)
    pool = perks_allowed_for_hired_rarity(hired_rarity)
    # Prefer at least one perk of matching rarity for U+
    must_rarity = int(hired_rarity)
    ids: list[str] = []
    if forced_legendary_id and forced_legendary_id in PERK_BY_ID:
        ids.append(forced_legendary_id)
    matching = [p for p in pool if p.rarity == must_rarity and p.id not in ids]
    if matching and len(ids) < slots:
        ids.append(rnd.choice(matching).id)
    while len(ids) < slots:
        candidates = [p for p in pool if p.id not in ids]
        if not candidates:
            break
        # weight toward higher rarity slightly
        weights = [1 + p.rarity for p in candidates]
        pick = rnd.choices(candidates, weights=weights, k=1)[0]
        ids.append(pick.id)
    return ids[:slots]


def catalog_public() -> list[dict]:
    return [
        {
            "id": p.id,
            "name": p.name_ru,
            "type": p.perk_type,
            "rarity": p.rarity,
            "tags": list(p.tags),
            "power_pct": p.power_pct,
            "flavor": p.flavor_ru,
        }
        for p in PERKS
    ]
