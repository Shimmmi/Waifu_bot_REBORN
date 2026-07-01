"""Игровые теги сложности экспедиций v1.4: мультитеги, отключение типов отрядом, гибридный урон."""
from __future__ import annotations

from typing import Any, Iterable, Sequence

from waifu_bot.db.models.waifu import WaifuClass, WaifuRace
from waifu_bot.game.expedition_data import AFFIX_BY_ID
from waifu_bot.game.expedition_redesign import (
    CHALLENGE_CATEGORIES,
    CLASS_COUNTERS,
    PERK_CHALLENGE_CATEGORIES,
    RACE_COUNTERS,
    best_perk_level_for_category,
    count_class_counters_for_category,
    count_race_counters_for_category,
)

# --- Канонические id тегов (8 типов) ---
TAG_MONSTERS = "monsters"
TAG_UNDEAD = "undead"
TAG_DARK_MAGIC = "dark_magic"
TAG_ELEMENTS = "elements"
TAG_TRAPS = "traps"
TAG_CURSES = "curses"
TAG_KNOWLEDGE = "knowledge"
TAG_SOCIAL = "social"

DIFFICULTY_TAG_IDS: tuple[str, ...] = (
    TAG_MONSTERS,
    TAG_UNDEAD,
    TAG_DARK_MAGIC,
    TAG_ELEMENTS,
    TAG_TRAPS,
    TAG_CURSES,
    TAG_KNOWLEDGE,
    TAG_SOCIAL,
)

DIFFICULTY_TAG_LABEL_RU: dict[str, str] = {
    TAG_MONSTERS: "Монстры",
    TAG_UNDEAD: "Нежить",
    TAG_DARK_MAGIC: "Тёмная магия",
    TAG_ELEMENTS: "Стихии",
    TAG_TRAPS: "Ловушки",
    TAG_CURSES: "Проклятия",
    TAG_KNOWLEDGE: "Знания",
    TAG_SOCIAL: "Социум",
}

# Тег → challenge-категории (для весов тика и tick_adj)
TAG_TO_CHALLENGE: dict[str, frozenset[str]] = {
    TAG_MONSTERS: frozenset({"enemy"}),
    TAG_UNDEAD: frozenset({"enemy", "cursed"}),
    TAG_DARK_MAGIC: frozenset({"cursed", "magic"}),
    TAG_ELEMENTS: frozenset({"magic", "nature"}),
    TAG_TRAPS: frozenset({"hazard"}),
    TAG_CURSES: frozenset({"cursed"}),
    TAG_KNOWLEDGE: frozenset({"knowledge"}),
    TAG_SOCIAL: frozenset({"social"}),
}

# Seed DB affixes by name (миграция 0026)
DB_AFFIX_NAME_TAGS: dict[str, frozenset[str]] = {
    "Огненная": frozenset({TAG_ELEMENTS}),
    "Ледяная": frozenset({TAG_ELEMENTS}),
    "Ядовитая": frozenset({TAG_ELEMENTS}),
    "Проклятая": frozenset({TAG_DARK_MAGIC, TAG_CURSES}),
    "Тёмная": frozenset({TAG_DARK_MAGIC, TAG_CURSES}),
    "Заброшенная": frozenset({TAG_TRAPS}),
    "Древняя": frozenset({TAG_KNOWLEDGE, TAG_SOCIAL}),
    "Туманная": frozenset({TAG_TRAPS}),
    "Затопленная": frozenset({TAG_ELEMENTS}),
    "Горящая": frozenset({TAG_ELEMENTS}),
    "с гоблинами": frozenset({TAG_MONSTERS}),
    "с разбойниками": frozenset({TAG_MONSTERS}),
    "с пауками": frozenset({TAG_MONSTERS}),
    "со змеями": frozenset({TAG_MONSTERS}),
    "с нежитью": frozenset({TAG_MONSTERS, TAG_UNDEAD}),
    "с демонами": frozenset({TAG_MONSTERS, TAG_DARK_MAGIC}),
    "с ловушками": frozenset({TAG_TRAPS}),
    "с огненными реками": frozenset({TAG_TRAPS, TAG_ELEMENTS}),
    "с призраками": frozenset({TAG_MONSTERS, TAG_UNDEAD}),
    "с охраной": frozenset({TAG_MONSTERS}),
    "с головоломками": frozenset({TAG_TRAPS, TAG_KNOWLEDGE}),
    "с сокровищами": frozenset({TAG_KNOWLEDGE, TAG_SOCIAL}),
}

# Legacy affix id → теги
LEGACY_AFFIX_ID_TAGS: dict[str, frozenset[str]] = {
    # environment
    "smelly": frozenset({TAG_ELEMENTS, TAG_TRAPS}),
    "flooded": frozenset({TAG_ELEMENTS}),
    "hot": frozenset({TAG_ELEMENTS}),
    "icy": frozenset({TAG_ELEMENTS}),
    "foggy": frozenset({TAG_TRAPS}),
    "stormy": frozenset({TAG_ELEMENTS, TAG_TRAPS}),
    "dusty": frozenset({TAG_ELEMENTS}),
    "poisonous_air": frozenset({TAG_ELEMENTS, TAG_TRAPS}),
    "snowstorm": frozenset({TAG_ELEMENTS}),
    "acid_rain": frozenset({TAG_ELEMENTS}),
    # creatures
    "evil_elves": frozenset({TAG_MONSTERS}),
    "orc_berserkers": frozenset({TAG_MONSTERS}),
    "undead": frozenset({TAG_MONSTERS, TAG_UNDEAD}),
    "demons": frozenset({TAG_MONSTERS, TAG_DARK_MAGIC}),
    "dragons": frozenset({TAG_MONSTERS}),
    "goblins": frozenset({TAG_MONSTERS}),
    "trolls": frozenset({TAG_MONSTERS}),
    "vampires": frozenset({TAG_MONSTERS, TAG_UNDEAD}),
    "giant_insects": frozenset({TAG_MONSTERS}),
    "bats": frozenset({TAG_MONSTERS}),
    # location
    "poisonous_mushrooms": frozenset({TAG_TRAPS, TAG_ELEMENTS}),
    "traps": frozenset({TAG_TRAPS}),
    "cursed_artifacts": frozenset({TAG_CURSES, TAG_KNOWLEDGE}),
    "quicksand": frozenset({TAG_TRAPS, TAG_ELEMENTS}),
    "spiderwebs": frozenset({TAG_TRAPS, TAG_MONSTERS}),
    "acid_pools": frozenset({TAG_TRAPS}),
    "magical_anomalies": frozenset({TAG_DARK_MAGIC, TAG_ELEMENTS}),
    "ghostly_phenomena": frozenset({TAG_UNDEAD, TAG_DARK_MAGIC}),
    "cave_ins": frozenset({TAG_TRAPS}),
    "magnetic_anomalies": frozenset({TAG_DARK_MAGIC, TAG_ELEMENTS}),
    # magical
    "cursed": frozenset({TAG_CURSES, TAG_DARK_MAGIC}),
    "enchanted": frozenset({TAG_DARK_MAGIC}),
    "distorted": frozenset({TAG_DARK_MAGIC}),
    "blinding": frozenset({TAG_DARK_MAGIC}),
    "paralyzing": frozenset({TAG_DARK_MAGIC}),
    "time_slow": frozenset({TAG_DARK_MAGIC}),
    "time_fast": frozenset({TAG_DARK_MAGIC}),
    "space_distortion": frozenset({TAG_DARK_MAGIC}),
    "mana_drain": frozenset({TAG_DARK_MAGIC}),
    "luck_curse": frozenset({TAG_CURSES, TAG_DARK_MAGIC}),
    # psychological
    "mental_attacks": frozenset({TAG_SOCIAL, TAG_CURSES}),
    "phobias": frozenset({TAG_SOCIAL, TAG_CURSES}),
    "hallucinations": frozenset({TAG_SOCIAL, TAG_CURSES}),
    "magic_sleep": frozenset({TAG_SOCIAL, TAG_DARK_MAGIC}),
    "paranoia": frozenset({TAG_SOCIAL}),
    "amnesia": frozenset({TAG_KNOWLEDGE}),
    "persecution_complex": frozenset({TAG_SOCIAL}),
    "depression": frozenset({TAG_SOCIAL}),
    "aggression": frozenset({TAG_SOCIAL}),
    "apathy": frozenset({TAG_SOCIAL}),
}

# Fallback DB category → теги
_DB_CATEGORY_TAGS: dict[str, frozenset[str]] = {
    "enemy": frozenset({TAG_MONSTERS}),
    "hazard": frozenset({TAG_TRAPS}),
    "cursed": frozenset({TAG_DARK_MAGIC, TAG_CURSES}),
    "elemental": frozenset({TAG_ELEMENTS}),
    "blessed": frozenset({TAG_KNOWLEDGE, TAG_SOCIAL}),
}

# Раса → теги (отключаемые типы)
RACE_TAG_COVERAGE: dict[int, frozenset[str]] = {
    int(WaifuRace.HUMAN): frozenset({TAG_KNOWLEDGE, TAG_SOCIAL}),
    int(WaifuRace.ELF): frozenset({TAG_ELEMENTS}),
    int(WaifuRace.BEASTKIN): frozenset({TAG_MONSTERS}),
    int(WaifuRace.ANGEL): frozenset({TAG_DARK_MAGIC}),
    int(WaifuRace.VAMPIRE): frozenset({TAG_DARK_MAGIC, TAG_UNDEAD}),
    int(WaifuRace.DEMON): frozenset({TAG_DARK_MAGIC, TAG_CURSES}),
    int(WaifuRace.FAIRY): frozenset({TAG_KNOWLEDGE, TAG_ELEMENTS, TAG_SOCIAL}),
}

# Класс → теги
CLASS_TAG_COVERAGE: dict[int, frozenset[str]] = {
    int(WaifuClass.KNIGHT): frozenset({TAG_MONSTERS}),
    int(WaifuClass.WARRIOR): frozenset({TAG_MONSTERS}),
    int(WaifuClass.ARCHER): frozenset({TAG_MONSTERS, TAG_ELEMENTS}),
    int(WaifuClass.MAGE): frozenset({TAG_DARK_MAGIC, TAG_CURSES}),
    int(WaifuClass.ASSASSIN): frozenset({TAG_TRAPS, TAG_SOCIAL}),
    int(WaifuClass.HEALER): frozenset({TAG_DARK_MAGIC}),
    int(WaifuClass.MERCHANT): frozenset({TAG_KNOWLEDGE, TAG_SOCIAL}),
}

# Перк → теги (включая алиасы ТЗ)
PERK_TAG_COVERAGE: dict[str, frozenset[str]] = {
    "gas_mask": frozenset({TAG_TRAPS, TAG_ELEMENTS}),
    "diver": frozenset({TAG_ELEMENTS}),
    "fireproof": frozenset({TAG_ELEMENTS}),
    "frostproof": frozenset({TAG_ELEMENTS}),
    "navigator": frozenset({TAG_TRAPS, TAG_KNOWLEDGE}),
    "desert_walker": frozenset({TAG_ELEMENTS}),
    "gas_filter": frozenset({TAG_TRAPS}),
    "snow_warrior": frozenset({TAG_MONSTERS, TAG_ELEMENTS}),
    "acid_proof": frozenset({TAG_ELEMENTS}),
    "wind_walker": frozenset({TAG_ELEMENTS}),
    "elf_slayer": frozenset({TAG_MONSTERS}),
    "orc_hunter": frozenset({TAG_MONSTERS}),
    "priest": frozenset({TAG_UNDEAD}),
    "demon_slayer": frozenset({TAG_MONSTERS, TAG_DARK_MAGIC}),
    "dragonslayer": frozenset({TAG_MONSTERS}),
    "goblin_shaker": frozenset({TAG_MONSTERS}),
    "troll_slayer": frozenset({TAG_MONSTERS}),
    "vampire_hunter": frozenset({TAG_UNDEAD, TAG_MONSTERS}),
    "entomologist": frozenset({TAG_MONSTERS, TAG_ELEMENTS}),
    "bat_hunter": frozenset({TAG_MONSTERS}),
    "mushroom_expert": frozenset({TAG_TRAPS, TAG_ELEMENTS}),
    "scout": frozenset({TAG_TRAPS}),
    "archaeologist": frozenset({TAG_CURSES, TAG_TRAPS, TAG_KNOWLEDGE}),
    "swamp_walker": frozenset({TAG_TRAPS, TAG_ELEMENTS}),
    "spider_hunter": frozenset({TAG_MONSTERS, TAG_TRAPS}),
    "chemist": frozenset({TAG_TRAPS, TAG_KNOWLEDGE}),
    "magic_researcher": frozenset({TAG_DARK_MAGIC, TAG_KNOWLEDGE}),
    "exorcist": frozenset({TAG_UNDEAD, TAG_DARK_MAGIC}),
    "mountain_engineer": frozenset({TAG_TRAPS}),
    "anti_magnet": frozenset({TAG_DARK_MAGIC, TAG_ELEMENTS}),
    "curse_removal": frozenset({TAG_CURSES, TAG_DARK_MAGIC}),
    "anti_mage": frozenset({TAG_DARK_MAGIC}),
    "spatial_mage": frozenset({TAG_DARK_MAGIC}),
    "light_protection": frozenset({TAG_DARK_MAGIC}),
    "magic_resistance": frozenset({TAG_DARK_MAGIC}),
    "chronomancer": frozenset({TAG_DARK_MAGIC, TAG_KNOWLEDGE}),
    "accelerator": frozenset({TAG_DARK_MAGIC}),
    "spatial_navigator": frozenset({TAG_DARK_MAGIC}),
    "mana_shield": frozenset({TAG_DARK_MAGIC}),
    "lucky": frozenset({TAG_KNOWLEDGE, TAG_SOCIAL}),
    "mental_shield": frozenset({TAG_SOCIAL, TAG_CURSES}),
    "strong_spirit": frozenset({TAG_SOCIAL, TAG_CURSES}),
    "mental_clarity": frozenset({TAG_SOCIAL, TAG_CURSES}),
    "sleepless": frozenset({TAG_SOCIAL, TAG_DARK_MAGIC}),
    "trusting": frozenset({TAG_SOCIAL}),
    "photographic_memory": frozenset({TAG_KNOWLEDGE}),
    "calm": frozenset({TAG_SOCIAL}),
    "optimist": frozenset({TAG_SOCIAL}),
    "anger_control": frozenset({TAG_SOCIAL}),
    "passionate": frozenset({TAG_SOCIAL}),
    # Алиасы из ТЗ (runtime, без отдельной записи в PERKS)
    "monster_slayer": frozenset({TAG_MONSTERS}),
    "undead_fighter": frozenset({TAG_UNDEAD}),
}

PERK_TAG_ALIASES: dict[str, str] = {
    "monster_slayer": "goblin_shaker",
    "undead_fighter": "priest",
}


def resolve_perk_id(perk_id: str) -> str:
    return PERK_TAG_ALIASES.get(perk_id, perk_id)


def tags_for_db_affix_row(row: Any) -> frozenset[str]:
    """Теги одной строки expedition_affixes."""
    stored = getattr(row, "difficulty_tags", None)
    if stored:
        valid = {str(t) for t in stored if str(t) in DIFFICULTY_TAG_LABEL_RU}
        if valid:
            return frozenset(valid)
    name = (getattr(row, "name", None) or "").strip()
    if name in DB_AFFIX_NAME_TAGS:
        return DB_AFFIX_NAME_TAGS[name]
    cat = (getattr(row, "category", None) or "").lower().strip()
    return _DB_CATEGORY_TAGS.get(cat, frozenset({TAG_MONSTERS}))


def union_affix_tags(affix_rows: Sequence[Any]) -> frozenset[str]:
    out: set[str] = set()
    for row in affix_rows:
        out |= tags_for_db_affix_row(row)
    return frozenset(out)


def union_legacy_affix_tags(affix_ids: Iterable[str]) -> frozenset[str]:
    out: set[str] = set()
    for aid in affix_ids:
        key = str(aid).strip() if aid else ""
        if not key:
            continue
        aff = AFFIX_BY_ID.get(key)
        if aff and key in LEGACY_AFFIX_ID_TAGS:
            out |= LEGACY_AFFIX_ID_TAGS[key]
        elif aff:
            cat = (aff.category or "").lower()
            if cat == "environment":
                out |= {TAG_ELEMENTS}
            elif cat == "creatures":
                out |= {TAG_MONSTERS}
                if key == "undead":
                    out.add(TAG_UNDEAD)
            elif cat == "location":
                out |= {TAG_TRAPS}
            elif cat == "magical":
                out |= {TAG_DARK_MAGIC, TAG_CURSES}
            elif cat == "psychological":
                out |= {TAG_SOCIAL, TAG_CURSES}
    return frozenset(out)


# Минимальный множитель урона при полном perk-покрытии всех тегов (v1.5)
TAG_MULT_FLOOR = 0.30


def unit_covered_tags(unit) -> frozenset[str]:
    """Union тегов сложности, которые закрывает одна наёмница (только перки)."""
    detail = unit_coverage_detail(unit)
    return frozenset(detail["covered_tags"])


def unit_coverage_detail(unit) -> dict:
    """Покрытие тегов одной наёмницы по источникам (для UI пикера экспедиций)."""
    race = int(getattr(unit, "race", 1) or 1)
    cls = int(getattr(unit, "class_", 1) or 1)
    race_tags = RACE_TAG_COVERAGE.get(race, frozenset())
    class_tags = CLASS_TAG_COVERAGE.get(cls, frozenset())
    perk_tags: dict[str, list[str]] = {}
    perk_union: set[str] = set()
    for p in getattr(unit, "perks", None) or []:
        pid = resolve_perk_id(str(p) if p is not None else "")
        if pid in PERK_TAG_COVERAGE:
            tags = PERK_TAG_COVERAGE[pid]
            perk_tags[pid] = sorted_tag_list(tags)
            perk_union |= tags
    covered = frozenset(perk_union)
    return {
        "race_tags": sorted_tag_list(race_tags),
        "class_tags": sorted_tag_list(class_tags),
        "perk_tags": perk_tags,
        "covered_tags": sorted_tag_list(covered),
    }


def squad_covered_tags(squad: Sequence) -> frozenset[str]:
    out: set[str] = set()
    for u in squad:
        out |= unit_covered_tags(u)
    return frozenset(out)


def calc_perk_affix_effectiveness(perk_level: int, affix_level: int) -> float:
    """Доля эффективности перка против уровня препятствия I–V (0..1)."""
    pl = max(0, int(perk_level or 0))
    al = max(1, int(affix_level or 1))
    if pl <= 0:
        return 0.0
    return min(1.0, pl / al)


def best_perk_level_for_tag(squad: Sequence, tag_id: str) -> int:
    """Макс. уровень перка отряда, покрывающего игровой тег."""
    best = 0
    for u in squad:
        perk_levels: dict = getattr(u, "perk_levels", None) or {}
        for p in getattr(u, "perks", None) or []:
            pid = resolve_perk_id(str(p) if p is not None else "")
            if pid in PERK_TAG_COVERAGE and tag_id in PERK_TAG_COVERAGE[pid]:
                best = max(best, int(perk_levels.get(pid, 1)))
    return best


def tag_coverage_effectiveness(squad: Sequence, tag_id: str, affix_level: int) -> float:
    """Эффективность perk-покрытия одного тега: min(1, perk_lv/affix_lv) или 0."""
    perk_lv = best_perk_level_for_tag(squad, tag_id)
    if perk_lv > 0:
        return calc_perk_affix_effectiveness(perk_lv, affix_level)
    return 0.0


def _tag_coverage_eff_sum(
    active_tags: frozenset[str],
    covered_tags: frozenset[str],
    *,
    squad: Sequence | None = None,
    affix_level: int = 1,
) -> float:
    eff_sum = 0.0
    for t in active_tags:
        if t not in covered_tags:
            continue
        if squad is None:
            eff = 1.0
        else:
            eff = tag_coverage_effectiveness(squad, t, affix_level)
        if eff > 0:
            eff_sum += eff
    return eff_sum


def calc_tag_coverage_ratio(
    active_tags: frozenset[str],
    covered_tags: frozenset[str],
    *,
    squad: Sequence | None = None,
    affix_level: int = 1,
) -> float:
    """Доля эффективного perk-покрытия активных тегов (0..1)."""
    if not active_tags:
        return 0.0
    return _tag_coverage_eff_sum(
        active_tags, covered_tags, squad=squad, affix_level=affix_level
    ) / len(active_tags)


def calc_tag_effectiveness_mult(
    active_tags: frozenset[str],
    covered_tags: frozenset[str],
    *,
    squad: Sequence | None = None,
    affix_level: int = 1,
) -> float:
    """
    Линейный бленд по доле perk-покрытия: tag_mult = max(floor, 1 - 0.95 × coverage_ratio).
    coverage_ratio = (Σ eff_t для t ∈ active ∩ covered) / N, N = |active_tags|.
    eff_t = min(1, perk_lv/affix_lv). Раса/класс не учитываются (только tick_adj).
    """
    if not active_tags:
        return 1.0
    coverage_ratio = calc_tag_coverage_ratio(
        active_tags, covered_tags, squad=squad, affix_level=affix_level
    )
    return max(TAG_MULT_FLOOR, 1.0 - 0.95 * coverage_ratio)


def tag_effectiveness_pct(
    active_tags: frozenset[str],
    covered_tags: frozenset[str],
    *,
    squad: Sequence | None = None,
    affix_level: int = 1,
) -> float:
    return round(
        calc_tag_effectiveness_mult(
            active_tags, covered_tags, squad=squad, affix_level=affix_level
        )
        * 100.0,
        1,
    )


def squad_perk_effectiveness_pct(
    active_tags: frozenset[str],
    covered_tags: frozenset[str],
    squad: Sequence,
    affix_level: int,
) -> float:
    """Средняя эффективность перков по активным покрытым тегам (для UI)."""
    covered_active = [t for t in active_tags if t in covered_tags]
    if not covered_active:
        return 0.0
    total = sum(tag_coverage_effectiveness(squad, t, affix_level) for t in covered_active)
    return round(total / len(covered_active) * 100.0, 1)


def _squad_has_challenge_counter(squad: Sequence, challenge_cat: str) -> bool:
    if count_race_counters_for_category(squad, challenge_cat) > 0:
        return True
    if count_class_counters_for_category(squad, challenge_cat) > 0:
        return True
    if best_perk_level_for_category(squad, challenge_cat, default_level=1) > 0:
        return True
    return False


def calc_tick_challenge_adj(
    challenge_cat: str,
    squad: Sequence,
    primary_categories: frozenset[str],
    affix_level: int = 1,
) -> float:
    """
    Гибрид v1.4/v1.5: −10% при контре расы/класса; перк масштабируется min(1, perk_lv/affix_lv).
    +10% если категория в primary слота без контра.
    """
    has_race = count_race_counters_for_category(squad, challenge_cat) > 0
    has_class = count_class_counters_for_category(squad, challenge_cat) > 0
    perk_lv = best_perk_level_for_category(squad, challenge_cat, default_level=0)
    in_primary = challenge_cat in primary_categories

    if has_race or has_class:
        return -0.10
    if perk_lv > 0:
        eff = calc_perk_affix_effectiveness(perk_lv, affix_level)
        return -0.10 * eff
    if in_primary:
        return 0.10
    return 0.0


def challenge_categories_boosted_by_tags(active_tags: frozenset[str]) -> frozenset[str]:
    out: set[str] = set()
    for tag in active_tags:
        out |= TAG_TO_CHALLENGE.get(tag, frozenset())
    return frozenset(out)


def sorted_tag_list(tags: frozenset[str]) -> list[str]:
    order = {t: i for i, t in enumerate(DIFFICULTY_TAG_IDS)}
    return sorted(tags, key=lambda t: order.get(t, 99))


def tags_to_labels(tag_ids: Iterable[str]) -> list[str]:
    return [DIFFICULTY_TAG_LABEL_RU.get(str(t), str(t)) for t in tag_ids if str(t) in DIFFICULTY_TAG_LABEL_RU]
