"""Экспедиции v1.3: урон по контру (раса/класс/перк), 7 категорий испытаний, тики 15 мин."""
from __future__ import annotations

import random
from typing import Any, Iterable, Sequence

from waifu_bot.db.models.waifu import WaifuClass, WaifuRace

# Уровень аффикса I–V → базовый % урона от суммарного HP отряда за событие
AFFIX_LEVEL_BASE_HP_PCT: dict[int, float] = {
    1: 0.06,
    2: 0.10,
    3: 0.15,
    4: 0.20,
    5: 0.28,
}

CHALLENGE_CATEGORIES: tuple[str, ...] = (
    "cursed",
    "enemy",
    "hazard",
    "knowledge",
    "magic",
    "nature",
    "social",
)

# Длительности (мин) и число событий (Fallout Shelter: шаг 15 мин)
EXPEDITION_V13_DURATIONS: tuple[int, ...] = (30, 45, 60, 90, 120)


def events_count_for_duration(duration_minutes: int) -> int:
    return max(1, duration_minutes // 15)


def roman_numeral(level: int) -> str:
    return ("I", "II", "III", "IV", "V")[max(0, min(4, level - 1))]


# Раса → категории, где даётся расовый контр (−8% за каждую подходящую наёмницу на событие)
RACE_COUNTERS: dict[int, frozenset[str]] = {
    int(WaifuRace.HUMAN): frozenset({"knowledge", "social"}),
    int(WaifuRace.ELF): frozenset({"magic", "nature"}),
    int(WaifuRace.BEASTKIN): frozenset({"enemy", "nature"}),
    int(WaifuRace.ANGEL): frozenset({"cursed"}),
    int(WaifuRace.VAMPIRE): frozenset({"cursed", "enemy"}),
    int(WaifuRace.DEMON): frozenset({"cursed", "magic"}),
    int(WaifuRace.FAIRY): frozenset({"knowledge", "nature", "social"}),
}

# Класс → категории классового контра (−15% за каждую подходящую наёмницу)
CLASS_COUNTERS: dict[int, frozenset[str]] = {
    int(WaifuClass.KNIGHT): frozenset({"enemy"}),
    int(WaifuClass.WARRIOR): frozenset({"enemy"}),
    int(WaifuClass.ARCHER): frozenset({"enemy", "nature"}),
    int(WaifuClass.MAGE): frozenset({"cursed", "magic"}),
    int(WaifuClass.ASSASSIN): frozenset({"hazard", "social"}),
    int(WaifuClass.HEALER): frozenset({"cursed", "hazard"}),
    int(WaifuClass.MERCHANT): frozenset({"knowledge", "social"}),
}

# Семейства перков для генерации при найме (веса по классу в CLASS_PERK_POOLS)
PERK_SKILL_FAMILIES: dict[str, str] = {
    # environment
    "gas_mask": "DEFENSE",
    "diver": "NATURE",
    "fireproof": "DEFENSE",
    "frostproof": "DEFENSE",
    "navigator": "LUCK",
    "desert_walker": "NATURE",
    "gas_filter": "DEFENSE",
    "snow_warrior": "COMBAT",
    "acid_proof": "DEFENSE",
    "wind_walker": "NATURE",
    # creatures
    "elf_slayer": "COMBAT",
    "orc_hunter": "COMBAT",
    "priest": "HEALING",
    "demon_slayer": "COMBAT",
    "dragonslayer": "COMBAT",
    "goblin_shaker": "COMBAT",
    "troll_slayer": "COMBAT",
    "vampire_hunter": "COMBAT",
    "entomologist": "NATURE",
    "bat_hunter": "COMBAT",
    # location
    "mushroom_expert": "NATURE",
    "scout": "STEALTH",
    "archaeologist": "KNOWLEDGE",
    "swamp_walker": "NATURE",
    "spider_hunter": "STEALTH",
    "chemist": "KNOWLEDGE",
    "magic_researcher": "MAGIC",
    "exorcist": "SPIRIT",
    "mountain_engineer": "TRAP",
    "anti_magnet": "MAGIC",
    # magical
    "curse_removal": "SPIRIT",
    "anti_mage": "MAGIC",
    "spatial_mage": "MAGIC",
    "light_protection": "MAGIC",
    "magic_resistance": "MAGIC",
    "chronomancer": "MAGIC",
    "accelerator": "MAGIC",
    "spatial_navigator": "MAGIC",
    "mana_shield": "MAGIC",
    "lucky": "LUCK",
    # psychological
    "mental_shield": "SOCIAL",
    "strong_spirit": "SPIRIT",
    "mental_clarity": "SOCIAL",
    "sleepless": "SOCIAL",
    "trusting": "SOCIAL",
    "photographic_memory": "KNOWLEDGE",
    "calm": "SOCIAL",
    "optimist": "SOCIAL",
    "anger_control": "SOCIAL",
    "passionate": "SOCIAL",
}

# Перк → категории испытаний, где перк даёт контр (для веса ×2 и perk_level в уроне)
PERK_CHALLENGE_CATEGORIES: dict[str, frozenset[str]] = {
    "gas_mask": frozenset({"hazard", "nature"}),
    "diver": frozenset({"hazard"}),
    "fireproof": frozenset({"hazard", "magic"}),
    "frostproof": frozenset({"hazard", "nature"}),
    "navigator": frozenset({"hazard", "knowledge"}),
    "desert_walker": frozenset({"hazard", "nature"}),
    "gas_filter": frozenset({"hazard"}),
    "snow_warrior": frozenset({"nature", "enemy"}),
    "acid_proof": frozenset({"hazard"}),
    "wind_walker": frozenset({"nature"}),
    "elf_slayer": frozenset({"enemy"}),
    "orc_hunter": frozenset({"enemy"}),
    "priest": frozenset({"cursed", "enemy"}),
    "demon_slayer": frozenset({"enemy", "magic"}),
    "dragonslayer": frozenset({"enemy"}),
    "goblin_shaker": frozenset({"enemy"}),
    "troll_slayer": frozenset({"enemy"}),
    "vampire_hunter": frozenset({"enemy", "cursed"}),
    "entomologist": frozenset({"enemy", "nature"}),
    "bat_hunter": frozenset({"enemy"}),
    "mushroom_expert": frozenset({"hazard", "nature"}),
    "scout": frozenset({"hazard"}),
    "archaeologist": frozenset({"hazard", "knowledge", "cursed"}),
    "swamp_walker": frozenset({"hazard", "nature"}),
    "spider_hunter": frozenset({"enemy", "hazard"}),
    "chemist": frozenset({"hazard", "knowledge"}),
    "magic_researcher": frozenset({"magic", "knowledge"}),
    "exorcist": frozenset({"cursed", "magic"}),
    "mountain_engineer": frozenset({"hazard"}),
    "anti_magnet": frozenset({"magic", "hazard"}),
    "curse_removal": frozenset({"cursed", "magic"}),
    "anti_mage": frozenset({"magic"}),
    "spatial_mage": frozenset({"magic", "hazard"}),
    "light_protection": frozenset({"magic", "hazard"}),
    "magic_resistance": frozenset({"magic"}),
    "chronomancer": frozenset({"magic", "knowledge"}),
    "accelerator": frozenset({"magic"}),
    "spatial_navigator": frozenset({"magic", "hazard"}),
    "mana_shield": frozenset({"magic"}),
    "lucky": frozenset({"knowledge", "social"}),
    "mental_shield": frozenset({"social", "cursed"}),
    "strong_spirit": frozenset({"social", "cursed"}),
    "mental_clarity": frozenset({"social", "cursed"}),
    "sleepless": frozenset({"social", "magic"}),
    "trusting": frozenset({"social"}),
    "photographic_memory": frozenset({"knowledge"}),
    "calm": frozenset({"social"}),
    "optimist": frozenset({"social"}),
    "anger_control": frozenset({"social"}),
    "passionate": frozenset({"social"}),
}

# Пулы семейств перков при генерации наёмницы по классу (сумма = 1.0)
CLASS_PERK_POOLS: dict[int, dict[str, float]] = {
    int(WaifuClass.KNIGHT): {"COMBAT": 0.50, "DEFENSE": 0.25, "LUCK": 0.10, "other": 0.15},
    int(WaifuClass.WARRIOR): {"COMBAT": 0.50, "DEFENSE": 0.25, "LUCK": 0.10, "other": 0.15},
    int(WaifuClass.ARCHER): {"NATURE": 0.40, "STEALTH": 0.25, "COMBAT": 0.20, "other": 0.15},
    int(WaifuClass.MAGE): {"MAGIC": 0.45, "SPIRIT": 0.25, "KNOWLEDGE": 0.20, "other": 0.10},
    int(WaifuClass.ASSASSIN): {"STEALTH": 0.40, "TRAP": 0.25, "LUCK": 0.20, "other": 0.15},
    int(WaifuClass.HEALER): {"HEALING": 0.45, "SPIRIT": 0.25, "NATURE": 0.15, "other": 0.15},
    int(WaifuClass.MERCHANT): {"TRADE": 0.40, "SOCIAL": 0.30, "KNOWLEDGE": 0.20, "other": 0.10},
}

# Семейство → id перков, если нет прямого совпадения с PERK_SKILL_FAMILIES
FAMILY_PERK_IDS: dict[str, tuple[str, ...]] = {
    "STEALTH": ("scout", "spider_hunter", "mental_clarity"),
    "TRAP": ("scout", "mountain_engineer", "spider_hunter"),
    "HEALING": ("priest", "chemist"),
    "TRADE": ("lucky", "trusting", "archaeologist"),
    "DEFENSE": ("gas_mask", "fireproof", "frostproof", "magic_resistance"),
    "COMBAT": ("goblin_shaker", "orc_hunter", "elf_slayer"),
    "SPIRIT": ("strong_spirit", "curse_removal", "exorcist", "priest"),
    "NATURE": ("entomologist", "desert_walker", "swamp_walker"),
    "MAGIC": ("anti_mage", "magic_researcher", "mana_shield"),
    "KNOWLEDGE": ("archaeologist", "chemist", "photographic_memory", "magic_researcher"),
    "LUCK": ("lucky",),
    "SOCIAL": ("trusting", "optimist", "mental_shield"),
}


def pick_perk_id_for_class(class_id: int, rng: random.Random | None = None) -> str:
    """Один перк при найме по весам класса (ТЗ v1.3)."""
    from waifu_bot.game.expedition_data import PERKS

    r = rng or random
    cid = int(class_id)
    pool = CLASS_PERK_POOLS.get(cid) or CLASS_PERK_POOLS[int(WaifuClass.WARRIOR)]
    families = list(pool.keys())
    weights = [pool[k] for k in families]
    fam = r.choices(families, weights=weights, k=1)[0]
    if fam == "other":
        return r.choice(PERKS).id
    candidates = [p.id for p in PERKS if PERK_SKILL_FAMILIES.get(p.id) == fam]
    if not candidates and fam in FAMILY_PERK_IDS:
        allow = set(FAMILY_PERK_IDS[fam])
        candidates = [p.id for p in PERKS if p.id in allow]
    if not candidates:
        return r.choice(PERKS).id
    return r.choice(candidates)


def _db_category_to_challenge_categories(db_cat: str | None) -> frozenset[str]:
    if not db_cat:
        return frozenset({"enemy"})
    c = db_cat.lower().strip()
    if c == "enemy":
        return frozenset({"enemy"})
    if c == "hazard":
        return frozenset({"hazard"})
    if c == "cursed":
        return frozenset({"cursed"})
    if c == "elemental":
        return frozenset({"magic", "nature"})
    if c == "blessed":
        return frozenset({"knowledge", "social"})
    return frozenset({"enemy"})


def union_challenge_categories_from_db_affix_rows(rows: Sequence[Any]) -> frozenset[str]:
    """Объединение challenge-категорий по всем строкам expedition_affixes (префикс+суффиксы слота)."""
    out: set[str] = set()
    for row in rows:
        cat = getattr(row, "category", None)
        out |= _db_category_to_challenge_categories(cat if isinstance(cat, str) else None)
    return frozenset(out)


def squad_perk_challenge_categories(perk_ids: Iterable[str | Any]) -> frozenset[str]:
    out: set[str] = set()
    for p in perk_ids:
        pid = str(p) if p is not None else ""
        if pid in PERK_CHALLENGE_CATEGORIES:
            out |= PERK_CHALLENGE_CATEGORIES[pid]
    return frozenset(out)


def weighted_challenge_category(
    *,
    primary_categories: frozenset[str],
    squad_categories: frozenset[str],
    tag_boosted_categories: frozenset[str] | None = None,
    rng: random.Random | None = None,
) -> str:
    """Выбор категории испытания: базовый вес 100, ×2 перк отряда, ×1.35 primary слота, ×1.25 теги слота."""
    r = rng or random
    weights: list[float] = []
    cats = list(CHALLENGE_CATEGORIES)
    tag_boost = tag_boosted_categories or frozenset()
    for cat in cats:
        w = 100.0
        if cat in squad_categories:
            w *= 2.0
        if cat in primary_categories:
            w *= 1.35
        if cat in tag_boost:
            w *= 1.25
        weights.append(w)
    return r.choices(cats, weights=weights, k=1)[0]


def calc_event_damage_v14(
    *,
    base_hp_pct: float,
    squad_hp_total: int,
    active_tags: frozenset[str],
    covered_tags: frozenset[str],
    challenge_cat: str,
    squad: Sequence,
    primary_categories: frozenset[str],
    affix_level: int = 1,
    rand_variance: float | None = None,
) -> int:
    """v1.4/v1.5: tag_mult × (1 + tick_adj) × rand; tick_adj и tag_mult учитывают уровень перка."""
    from waifu_bot.game.expedition_difficulty_tags import (
        calc_tag_effectiveness_mult,
        calc_tick_challenge_adj,
    )

    tag_mult = calc_tag_effectiveness_mult(
        active_tags, covered_tags, squad=squad, affix_level=affix_level
    )
    tick_adj = calc_tick_challenge_adj(
        challenge_cat, squad, primary_categories, affix_level=affix_level
    )
    rv = rand_variance if rand_variance is not None else random.uniform(0.85, 1.15)
    mult = tag_mult * (1.0 + tick_adj) * rv
    base_damage = float(squad_hp_total) * base_hp_pct
    return max(1, round(base_damage * mult))


def count_race_counters_for_category(squad: Sequence, category: str) -> int:
    n = 0
    for u in squad:
        race = int(getattr(u, "race", 1) or 1)
        if category in RACE_COUNTERS.get(race, frozenset()):
            n += 1
    return n


def count_class_counters_for_category(squad: Sequence, category: str) -> int:
    n = 0
    for u in squad:
        cls = int(getattr(u, "class_", 1) or 1)
        if category in CLASS_COUNTERS.get(cls, frozenset()):
            n += 1
    return n


def best_perk_level_for_category(squad: Sequence, category: str, default_level: int = 1) -> int:
    """Макс. уровень перка (perk_levels на наёмнице), релевантного категории испытания."""
    best = 0
    for u in squad:
        perk_levels: dict = getattr(u, "perk_levels", None) or {}
        for p in getattr(u, "perks", None) or []:
            pid = str(p) if p is not None else ""
            if not pid:
                continue
            cats = PERK_CHALLENGE_CATEGORIES.get(pid)
            if cats and category in cats:
                lv = int(perk_levels.get(pid, default_level))
                best = max(best, lv)
    return best


def calc_event_damage(
    *,
    base_hp_pct: float,
    squad_hp_total: int,
    race_counters: int,
    class_counters: int,
    perk_level: int,
    difficulty_level: int,
    rand_variance: float | None = None,
) -> int:
    mult = 1.0
    mult *= (1 - 0.08) ** race_counters
    mult *= (1 - 0.15) ** class_counters
    if perk_level > 0:
        effectiveness = min(1.0, perk_level / max(1, difficulty_level))
        mult *= 1 - 0.35 * effectiveness
    rv = rand_variance if rand_variance is not None else random.uniform(0.85, 1.15)
    mult *= rv
    base_damage = float(squad_hp_total) * base_hp_pct
    return max(1, round(base_damage * mult))


def distribute_damage_to_squad(squad: Sequence, total_damage: int) -> dict[int, int]:
    """Распределяет суммарный урон пропорционально max_hp."""
    if total_damage <= 0:
        return {}
    units = list(squad)
    if not units:
        return {}
    weights = [max(1, int(getattr(u, "max_hp", 1) or 1)) for u in units]
    s = float(sum(weights))
    out: dict[int, int] = {}
    remaining = total_damage
    for i, u in enumerate(units):
        uid = int(getattr(u, "id", 0) or 0)
        if i == len(units) - 1:
            dmg = remaining
        else:
            dmg = int(round(total_damage * (weights[i] / s)))
            dmg = min(dmg, remaining)
            remaining -= dmg
        out[uid] = max(0, dmg)
    return out


def twist_roll(rng: random.Random | None = None) -> dict[str, Any] | None:
    """10% случайный твист."""
    r = rng or random
    if r.random() >= 0.10:
        return None
    twists = [
        {"type": "treasure", "text": "Обнаружен тайник", "reward_mult": 1.5},
        {"type": "npc", "text": "Встреча с путником", "reward_add": "item"},
        {"type": "shortcut", "text": "Найден проход", "skip_next_damage": True},
        {"type": "rest", "text": "Привал у родника", "hp_restore_pct": 0.15},
        {"type": "discovery", "text": "Древний артефакт", "exp_mult": 2.0},
    ]
    return r.choice(twists)


def affix_display_icon(affix_row: Any) -> str:
    """Иконка по категории аффикса в БД (карточка)."""
    c = (getattr(affix_row, "category", None) or "").lower()
    icons = {
        "enemy": "⚔️",
        "hazard": "⚠️",
        "cursed": "🌑",
        "elemental": "🔥",
        "blessed": "✨",
        "knowledge": "📜",
        "magic": "🔮",
        "nature": "🌿",
        "social": "💬",
    }
    return icons.get(c, "🏷️")


# biome_tag из слота → эмодзи для карточек / модалок
BIOME_EMOJI: dict[str, str] = {
    "cave": "🕳",
    "forest": "🌲",
    "ruins": "🏛",
    "swamp": "🍃",
    "temple": "⛪",
    "dark_temple": "🏚",
    "mountain": "⛰",
    "desert": "🏜",
    "dungeon": "🗝",
    "coast": "🌊",
    "urban": "🏙",
    "indoor": "🏠",
    "arctic": "🧊",
    "tundra": "❄",
    "volcano": "🌋",
    "crypt": "⚰",
    "fortress": "🏰",
    "sky": "☁",
    "sea_depth": "🐚",
    "abyss": "🕳",
}


def biome_emoji_for_tag(biome_tag: str | None) -> str:
    if not biome_tag:
        return "🗺"
    key = str(biome_tag).strip().lower().replace(" ", "_").replace("-", "_")
    return BIOME_EMOJI.get(key, "🗺")
