"""Каталог архетипов локаций и режимов экспедиции для ИИ-нарратива."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LocationArchetype:
    id: str
    name_ru: str
    biome_tag: str
    weight: int
    narrative_hints: tuple[str, ...]
    compatible_modes: tuple[str, ...] | None = None  # None = все режимы


@dataclass(frozen=True)
class ExpeditionMode:
    id: str
    name_ru: str
    weight: int
    narrative_focus: str
    prompt_rules_ru: str


@dataclass(frozen=True)
class ExpeditionNarrativeStyle:
    id: int
    name_ru: str
    prompt_rules_ru: str


EXPEDITION_NARRATIVE_STYLES: tuple[ExpeditionNarrativeStyle, ...] = (
    ExpeditionNarrativeStyle(
        1,
        "Канцелярский журнал квестов",
        "Пиши как бюрократический журнал заданий гильдии: пункты, формулировки «в соответствии с регламентом», "
        "но с абсурдными деталями и гротескным юмором.",
    ),
    ExpeditionNarrativeStyle(
        2,
        "Бардическая одиссея",
        "Пиши как бард, декламирующий одиссею: ритмичные обороты, гиперболы, драматические паузы — "
        "но с самоиронией и нишевым юмором.",
    ),
    ExpeditionNarrativeStyle(
        3,
        "Подкаст «true crime»",
        "Пиши как ведущий true crime подкаста: «сегодня мы разберём странное дело», нагнетание, "
        "улики и подозрительные детали — с гротескным юмором.",
    ),
    ExpeditionNarrativeStyle(
        4,
        "Тревел-влог",
        "Пиши как блогер-путешественник: «привет, друзья», обзор локации, советы и кадры «с места» — "
        "с абсурдными советами и самоиронией.",
    ),
    ExpeditionNarrativeStyle(
        5,
        "История пьяного трактирщика",
        "Пиши как трактирщик, рассказывающий историю за кружкой: «я вам скажу, но это между нами», "
        "преувеличения и путаница в деталях — с гротескным юмором.",
    ),
    ExpeditionNarrativeStyle(
        6,
        "Документалка о природе",
        "Пиши как закадровый голос документалки BBC о дикой природе: «здесь обитает…», "
        "научно-высокопарный тон и неожиданные сравнения — с абсурдным юмором.",
    ),
    ExpeditionNarrativeStyle(
        7,
        "Корпоративная переписка",
        "Пиши как переписку в корпоративном Slack: «коллеги», KPI, дедлайны, «синк в 15:00» — "
        "но про фэнтезийную экспедицию, с гротескным юмором.",
    ),
    ExpeditionNarrativeStyle(
        8,
        "Мыльная опера",
        "Пиши как мыльную оперу: драматические паузы, «он не знал, что…», внезапные повороты — "
        "с преувеличенными эмоциями и нишевым юмором.",
    ),
    ExpeditionNarrativeStyle(
        9,
        "Нуар-детектив",
        "Пиши как монолог нуар-детектива: дождь, тени, циничные наблюдения — "
        "с гротескными метафорами и самоиронией.",
    ),
    ExpeditionNarrativeStyle(
        10,
        "Игровой стрим",
        "Пиши как стример на Twitch: «чат, смотрите», реакции на происходящее, «это RNG», "
        "мемные обороты — с гротескным юмором.",
    ),
)

STYLE_BY_ID: dict[int, ExpeditionNarrativeStyle] = {s.id: s for s in EXPEDITION_NARRATIVE_STYLES}


EXPEDITION_LOCATION_ARCHETYPES: tuple[LocationArchetype, ...] = (
    # Городская / бытовая
    LocationArchetype("city", "Город", "urban", 100, ("улицы", "толпа", "фонари", "переулки")),
    LocationArchetype("slums", "Трущобы", "urban", 80, ("лачуги", "канализация", "контрабанда")),
    LocationArchetype("market", "Рынок", "urban", 90, ("лавки", "торг", "запахи специй")),
    LocationArchetype("night_club", "Ночной клуб", "urban", 70, ("неон", "музыка", "VIP-залы")),
    LocationArchetype("theater", "Театр", "indoor", 60, ("сцена", "кулисы", "маски")),
    LocationArchetype("harbor", "Гавань", "coast", 85, ("причалы", "чайки", "контейнеры")),
    LocationArchetype("train_station", "Вокзал", "urban", 75, ("платформы", "расписание", "толпа")),
    LocationArchetype("bridge_town", "Город на мосту", "urban", 55, ("висячие дома", "пропасть", "ветер")),
    LocationArchetype("casino", "Казино", "indoor", 50, ("рулетка", "фишки", "криминал")),
    LocationArchetype("graveyard", "Кладбище", "crypt", 65, ("надгробия", "туман", "старые могилы")),
    # Дикая природа
    LocationArchetype("forest", "Лес", "forest", 100, ("чаща", "тропы", "эхо")),
    LocationArchetype("jungle", "Джунгли", "forest", 80, ("лианы", "влажность", "хищники")),
    LocationArchetype("mountains", "Горы", "mountain", 90, ("обрывы", "ветер", "перевалы")),
    LocationArchetype("arctic", "Арктика", "arctic", 60, ("лед", "метель", "одиночество")),
    LocationArchetype("desert", "Пустыня", "desert", 70, ("дюны", "жара", "миражи")),
    LocationArchetype("swamp", "Болота", "swamp", 75, ("трясина", "туман", "болотный газ")),
    LocationArchetype("coast", "Побережье", "coast", 85, ("прилив", "скалы", "маяки")),
    LocationArchetype("volcano", "Вулкан", "volcano", 50, ("лава", "пепел", "жар")),
    LocationArchetype("tundra", "Тундра", "tundra", 55, ("мох", "холод", "простор")),
    LocationArchetype("dark_forest", "Тёмный лес", "forest", 70, ("сумрак", "корни", "шёпот")),
    # Подземное / руины
    LocationArchetype("cave", "Пещера", "cave", 95, ("сталактиты", "эхо", "темнота")),
    LocationArchetype("catacombs", "Катакомбы", "crypt", 75, ("кости", "узкие ходы", "свечи")),
    LocationArchetype("ruins", "Руины", "ruins", 100, ("обвалившиеся стены", "артефакты", "пыль")),
    LocationArchetype("mine", "Шахта", "cave", 70, ("рельсы", "забои", "газ")),
    LocationArchetype("sewer", "Канализация", "cave", 65, ("трубы", "сток", "крысы")),
    LocationArchetype("crypt", "Склеп", "crypt", 60, ("саркофаги", "печати", "холод")),
    # Магическое / фантастическое
    LocationArchetype("mage_tower", "Башня мага", "indoor", 80, ("руны", "книги", "эксперименты")),
    LocationArchetype("enchanted_garden", "Зачарованный сад", "forest", 65, ("цветы", "иллюзии", "феи")),
    LocationArchetype("floating_island", "Парящий остров", "sky", 45, ("пропасть", "ветер", "облака")),
    LocationArchetype("sky_castle", "Небесный замок", "sky", 40, ("облачные мосты", "высота", "башни")),
    LocationArchetype("fae_realm", "Царство фей", "forest", 50, ("гламур", "обман", "пир")),
    LocationArchetype("demon_gate", "Врата демонов", "abyss", 40, ("трещины", "сера", "шёпот")),
    LocationArchetype("crystal_caves", "Кристальные пещеры", "cave", 55, ("сияние", "резонанс", "отражения")),
    LocationArchetype("abyss", "Бездна", "abyss", 35, ("пустота", "эхо без ответа", "головокружение")),
    # Институции / социум
    LocationArchetype("temple", "Храм", "ruins", 80, ("алтарь", "молитвы", "священники")),
    LocationArchetype("monastery", "Монастырь", "fortress", 60, ("кельи", "молчание", "сад")),
    LocationArchetype("university", "Университет", "indoor", 70, ("аудитории", "архивы", "студенты")),
    LocationArchetype("palace", "Дворец", "fortress", 75, ("тронный зал", "интриги", "охрана")),
    LocationArchetype("prison", "Тюрьма", "fortress", 55, ("камеры", "решётки", "бунт")),
    LocationArchetype("hospital", "Лазарет", "indoor", 50, ("палаты", "запах трав", "раненые")),
    # Экзотика / нестандарт
    LocationArchetype("carnival", "Карнавал", "urban", 55, ("аттракционы", "маски", "фокусники")),
    LocationArchetype("factory", "Фабрика", "indoor", 60, ("конвейеры", "пар", "шум")),
    LocationArchetype("library", "Библиотека", "indoor", 65, ("полки", "пыльные тома", "тишина")),
    LocationArchetype("observatory", "Обсерватория", "indoor", 50, ("телескоп", "звёзды", "карты неба")),
    LocationArchetype("arena", "Арена", "fortress", 70, ("трибуны", "песок", "крики")),
    LocationArchetype("shipwreck", "Затонувший корабль", "sea_depth", 45, ("корпус", "водоросли", "сокровища")),
    LocationArchetype("underwater_city", "Подводный город", "sea_depth", 40, ("купол", "руины", "давление")),
    LocationArchetype("fortress", "Крепость", "fortress", 85, ("стены", "гарнизон", "осада")),
    LocationArchetype("lighthouse", "Маяк", "coast", 55, ("луч света", "скалы", "шторм")),
    LocationArchetype("vineyard", "Виноградник", "forest", 50, ("лозы", "бочки", "урожай")),
)

EXPEDITION_MODES: tuple[ExpeditionMode, ...] = (
    ExpeditionMode(
        "research",
        "Исследование",
        100,
        "открытия, карты, загадки",
        "Фокус на открытиях и загадках; бой — редкое осложнение, не главный конфликт. "
        "Не превращай сцену в классическое подземелье с ордами монстров.",
    ),
    ExpeditionMode(
        "combat",
        "Боевая",
        90,
        "столкновения, тактика, угрозы",
        "Допустимы сражения, но разнообразь их: засады, дуэли, тактика — не «коридор с гоблинами». "
        "Учитывай архетип локации, а не шаблонное подземелье.",
    ),
    ExpeditionMode(
        "social",
        "Социальная",
        95,
        "переговоры, интриги, NPC",
        "Конфликт через диалог, интригу, репутацию. Избегай массовых битв и «орды врагов».",
    ),
    ExpeditionMode(
        "salvage",
        "Добыча",
        85,
        "ценности, риск ради награды",
        "Мотивация — добыча и риск; опасности ситуативные, не обязательно монстры.",
    ),
    ExpeditionMode(
        "escort",
        "Эскорт",
        75,
        "защита груза или персоны",
        "Отряд охраняет кого-то или что-то; угрозы — помехи на пути, не бесконечные волны.",
    ),
    ExpeditionMode(
        "infiltration",
        "Скрытная",
        80,
        "проникновение, маскировка",
        "Напряжение от скрытности; провал — разоблачение, погоня, ловушки — не открытый штурм.",
    ),
    ExpeditionMode(
        "rescue",
        "Спасательная",
        85,
        "поиск пропавших, дедлайн",
        "Срочность и поиск; препятствия логичны для места, не generic dungeon crawl.",
    ),
    ExpeditionMode(
        "arcane",
        "Магическая",
        80,
        "ритуалы, аномалии, артефакты",
        "Магия и аномалии в центре; монстры — следствие магии, не «рандомная нежить».",
    ),
    ExpeditionMode(
        "trade",
        "Торговая",
        70,
        "сделки, контрабанда, рынок",
        "Конфликт через сделки, обман, таможню; минимум мечей ради мечей.",
    ),
    ExpeditionMode(
        "survival",
        "Выживание",
        75,
        "ресурсы, стихия, attrition",
        "Стихия и нехватка ресурсов; враги — вторичны по сравнению со средой.",
    ),
    ExpeditionMode(
        "investigation",
        "Расследование",
        90,
        "улики, версии, разоблачение",
        "Детективная линия: улики, подозреваемые; бой — если логичен, не по умолчанию.",
    ),
    ExpeditionMode(
        "sabotage",
        "Диверсия",
        65,
        "демонтаж, подрыв, хитрость",
        "Цель — саботаж или диверсия; скрытность и хитрость важнее прямого боя.",
    ),
)

ARCHETYPE_BY_ID: dict[str, LocationArchetype] = {a.id: a for a in EXPEDITION_LOCATION_ARCHETYPES}
MODE_BY_ID: dict[str, ExpeditionMode] = {m.id: m for m in EXPEDITION_MODES}

# Обратная совместимость: старые base_location → archetype id
LEGACY_BASE_LOCATION_TO_ARCHETYPE: dict[str, str] = {
    "Пещера": "cave",
    "Руины": "ruins",
    "Лес": "forest",
    "Болото": "swamp",
    "Крепость": "fortress",
    "Храм": "temple",
    "Катакомбы": "catacombs",
    "Шахта": "mine",
    "Пустыня": "desert",
    "Вулкан": "volcano",
    "Бездна": "abyss",
    "Воздушный замок": "sky_castle",
    "Морское дно": "underwater_city",
    "Тундра": "tundra",
}


def pick_location_archetype(rng: random.Random | None = None) -> LocationArchetype:
    r = rng or random.Random()
    weights = [a.weight for a in EXPEDITION_LOCATION_ARCHETYPES]
    return r.choices(list(EXPEDITION_LOCATION_ARCHETYPES), weights=weights, k=1)[0]


def pick_expedition_mode(
    rng: random.Random | None = None,
    *,
    preferred_mode_ids: tuple[str, ...] | None = None,
) -> ExpeditionMode:
    r = rng or random.Random()
    pool = list(EXPEDITION_MODES)
    if preferred_mode_ids:
        filtered = [m for m in pool if m.id in preferred_mode_ids]
        if filtered:
            pool = filtered
    weights = [m.weight for m in pool]
    return r.choices(pool, weights=weights, k=1)[0]


def archetype_for_id(archetype_id: str | None) -> LocationArchetype | None:
    if not archetype_id:
        return None
    return ARCHETYPE_BY_ID.get(str(archetype_id).strip())


def mode_for_id(mode_id: str | None) -> ExpeditionMode | None:
    if not mode_id:
        return None
    return MODE_BY_ID.get(str(mode_id).strip())


def archetype_from_legacy_name(name: str | None) -> LocationArchetype | None:
    if not name:
        return None
    key = name.strip()
    aid = LEGACY_BASE_LOCATION_TO_ARCHETYPE.get(key)
    if aid:
        return ARCHETYPE_BY_ID.get(aid)
    for arch in EXPEDITION_LOCATION_ARCHETYPES:
        if arch.name_ru.lower() == key.lower():
            return arch
    return None


def slot_preview_name(mode: ExpeditionMode, archetype: LocationArchetype) -> str:
    return f"{mode.name_ru} · {archetype.name_ru}"


def pick_narrative_style(rng: random.Random | None = None) -> ExpeditionNarrativeStyle:
    r = rng or random.Random()
    return r.choice(list(EXPEDITION_NARRATIVE_STYLES))


def narrative_style_for_id(style_id: int | None) -> ExpeditionNarrativeStyle | None:
    if style_id is None:
        return None
    try:
        return STYLE_BY_ID.get(int(style_id))
    except (TypeError, ValueError):
        return None


def narrative_style_prompt_block(style: ExpeditionNarrativeStyle) -> str:
    return f"Стиль повествования «{style.name_ru}»: {style.prompt_rules_ru}"


def fallback_narrative_brief(
    archetype: LocationArchetype,
    mode: ExpeditionMode,
    events_total: int,
    *,
    affix_names: list[str] | None = None,
    rng: random.Random | None = None,
    narrative_style: ExpeditionNarrativeStyle | None = None,
    squad_names: list[str] | None = None,
) -> dict:
    """Детерминированный бриф без ИИ."""
    r = rng or random.Random()
    style = narrative_style or pick_narrative_style(r)
    hints = list(archetype.narrative_hints)
    r.shuffle(hints)
    affix_bit = ""
    if affix_names:
        affix_bit = f" ({', '.join(affix_names[:2])})"
    title = f"{mode.name_ru} в {archetype.name_ru}{affix_bit}".strip()
    setting = (
        f"Отряд отправляется в {archetype.name_ru.lower()}: {hints[0] if hints else 'неизвестная зона'}. "
        f"Цель — {mode.narrative_focus}."
    )
    squad_bit = ""
    if squad_names:
        squad_bit = f" В составе: {', '.join(squad_names[:5])}."
    intro = (
        f"Брифинг перед выходом: {setting}{squad_bit} "
        f"Впереди — {mode.narrative_focus}, и это будет рассказано в стиле «{style.name_ru.lower()}»."
    )
    beats: list[str] = []
    for i in range(max(1, events_total)):
        hint = hints[i % len(hints)] if hints else "развитие сюжета"
        beats.append(f"Эпизод {i + 1}: {hint} в духе «{mode.name_ru.lower()}»")
    return {
        "title": title[:120],
        "setting_summary": setting,
        "intro_narrative": intro[:800],
        "key_elements": hints[:4],
        "event_beats": beats,
        "tone": style.name_ru[:64],
        "avoid_tropes": ["классическое подземелье", "орда гоблинов в коридоре"],
        "narrative_style_id": style.id,
        "narrative_style_name": style.name_ru,
    }


def resolve_archetype_and_mode(
    *,
    location_archetype_id: str | None = None,
    expedition_mode_id: str | None = None,
    legacy_base_location: str | None = None,
    rng: random.Random | None = None,
) -> tuple[LocationArchetype, ExpeditionMode]:
    r = rng or random.Random()
    arch = archetype_for_id(location_archetype_id)
    if not arch and legacy_base_location:
        arch = archetype_from_legacy_name(legacy_base_location)
    if not arch:
        arch = pick_location_archetype(r)
    mode = mode_for_id(expedition_mode_id) or pick_expedition_mode(r)
    if arch.compatible_modes:
        mode = pick_expedition_mode(r, preferred_mode_ids=arch.compatible_modes)
    return arch, mode
