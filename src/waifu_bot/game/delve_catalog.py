"""Delve column: copy bible, tap caps, sawtooth theater. GET never calls a language model."""

from __future__ import annotations

import hashlib
import html
import math
import random
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence
from zoneinfo import ZoneInfo

from waifu_bot.game.formulas import calculate_experience_for_level

MSK = ZoneInfo("Europe/Moscow")
DAY_SEC = 86_400

SPRITE_CAP = 9
REFORM_CD_DAYS = 21
UNLOCK_OV_LEVEL = 5

GOLD_OF_CHAT_CAP_DEFAULT = 0.25
CHAT_DAILY_POINTS_CAP_DEFAULT = 600
CHAT_GOLD_PER_POINT_DEFAULT = 2
CHAT_GOLD_CAP_DEFAULT = CHAT_DAILY_POINTS_CAP_DEFAULT * CHAT_GOLD_PER_POINT_DEFAULT  # 1200
GOLD_CAP_DAY_DEFAULT = int(GOLD_OF_CHAT_CAP_DEFAULT * CHAT_GOLD_CAP_DEFAULT)  # 300
XP_OF_SOLO_DAY_DEFAULT = 0.15
# Typical chat-dungeon day ≈ two next-level XP steps. Column XP = 15% of that.
SOLO_XP_DAY_K = 2.0

D0 = 24.0
ALPHA = 0.42
T0_SEC = 720.0
T_UP_SEC = 6.0
DEPTH_EXP = 1.15
VIEWPORT_NODES = 14
CEILING_TAIL_HOURS = 168.0
CEILING_TAIL_K = 0.8
CEILING_TAIL_EXP = 0.72

NODE_SURFACE = "SURFACE"
NODE_BOSS = "BOSS"
NODE_BRANCH = "BRANCH"
NODE_LANDMARK = "LANDMARK"
NODE_REST = "REST"
NODE_SHOP = "SHOP"
NODE_TRAVERSE = "TRAVERSE"
NODE_COMBAT = "COMBAT"

STATE_DESCENDING = "DESCENDING"
STATE_ASCENDING = "ASCENDING"
STATE_REST = "SURFACE_REST"

_BASE_LANDMARKS = (7, 13, 23, 37, 47, 67, 83, 97)

STANCES: dict[str, dict[str, str]] = {
    "scout": {"id": "scout", "label": "Разведчица", "blurb": "Идёт первой"},
    "shield": {"id": "shield", "label": "Со щитом", "blurb": "Держит строй"},
    "guide": {"id": "guide", "label": "Проводница", "blurb": "Помнит путь"},
}
TEMPERS: dict[str, dict[str, str]] = {
    "curiosity": {"id": "curiosity", "label": "Любопытство"},
    "temper": {"id": "temper", "label": "Вспыльчивость"},
    "stay": {"id": "stay", "label": "Стойкость"},
}
CLOAK_COLORS = ("ash", "wine", "moss", "ink")

# Chronicle → Delve on cutover.
STANCE_FROM_ROLE = {"blade": "scout", "witness": "guide", "keeper": "shield"}
TEMPER_FROM_MOTIVE = {
    "oath": "stay",
    "duty": "stay",
    "rival": "temper",
    "testimony": "temper",
    "absence": "curiosity",
    "sacrifice": "curiosity",
}

PALETTES: tuple[dict[str, str], ...] = (
    {"id": "mushrooms", "label": "Грибница", "shaft": "#2d4a32", "accent": "#7ec27a"},
    {"id": "crystal", "label": "Кристаллы", "shaft": "#2a3a58", "accent": "#8ec6ff"},
    {"id": "coal", "label": "Угольная шахта", "shaft": "#2a2420", "accent": "#c47a3a"},
    {"id": "wet", "label": "Мокрый колодец", "shaft": "#1e3a40", "accent": "#6ec4c0"},
    {"id": "ash", "label": "Пепелище", "shaft": "#3a3a3a", "accent": "#c8c2b4"},
    {"id": "limestone", "label": "Известняк", "shaft": "#4a4336", "accent": "#e0d2a8"},
)
PALETTE_IDS: tuple[str, ...] = tuple(p["id"] for p in PALETTES)
PALETTE_BY_ID: dict[str, dict[str, str]] = {p["id"]: p for p in PALETTES}

# Depth-band shaft art. Labels follow the image prompts (wet well, fungal shelves, …).
# Player palette only tints overlay.
SHAFT_BIOMES: tuple[dict[str, Any], ...] = (
    {"band": 10, "id": "wet", "label": "Мокрый колодец", "place_ru": "в мокром колодце", "file": "shaft.webp"},
    {"band": 20, "id": "mushrooms", "label": "Грибница", "place_ru": "среди грибов", "file": "shaft_20.webp"},
    {"band": 30, "id": "crystal", "label": "Кристаллы", "place_ru": "между кристаллами", "file": "shaft_30.webp"},
    {"band": 40, "id": "coal", "label": "Угольная шахта", "place_ru": "в угольной пыли", "file": "shaft_40.webp"},
    {"band": 50, "id": "ash", "label": "Пепелище", "place_ru": "в пепле", "file": "shaft_50.webp"},
    {"band": 60, "id": "limestone", "label": "Известняк", "place_ru": "в известняке", "file": "shaft_60.webp"},
    {"band": 70, "id": "ice", "label": "Ледник", "place_ru": "на льду", "file": "shaft_70.webp"},
    {"band": 80, "id": "magma", "label": "Магма", "place_ru": "у магмы", "file": "shaft_80.webp"},
    {"band": 90, "id": "bone", "label": "Катакомбы", "place_ru": "среди костей", "file": "shaft_90.webp"},
    {"band": 100, "id": "abyss", "label": "Бездна", "place_ru": "над бездной", "file": "shaft_100.webp"},
    {"band": 125, "id": "rust", "label": "Ржавый колодец", "place_ru": "в ржавом колодце", "file": "shaft_125.webp"},
    {"band": 150, "id": "salt", "label": "Соляная шахта", "place_ru": "в соляной корке", "file": "shaft_150.webp"},
    {"band": 200, "id": "amber", "label": "Янтарь", "place_ru": "в янтаре", "file": "shaft_200.webp"},
    {"band": 250, "id": "archive", "label": "Бумажный архив", "place_ru": "среди бумаг", "file": "shaft_250.webp"},
    {"band": 300, "id": "tar", "label": "Смоляной колодец", "place_ru": "в смоле", "file": "shaft_300.webp"},
    {"band": 350, "id": "porcelain", "label": "Битый фарфор", "place_ru": "в фарфоре", "file": "shaft_350.webp"},
    {"band": 400, "id": "verdigris", "label": "Медная патина", "place_ru": "в медной патине", "file": "shaft_400.webp"},
    {"band": 450, "id": "felt", "label": "Войлок", "place_ru": "в войлоке", "file": "shaft_450.webp"},
    {"band": 500, "id": "nacre", "label": "Перламутр", "place_ru": "в перламутре", "file": "shaft_500.webp"},
    {"band": 600, "id": "wax", "label": "Восковой колодец", "place_ru": "в воске", "file": "shaft_600.webp"},
    {"band": 700, "id": "graphite", "label": "Графит", "place_ru": "в графите", "file": "shaft_700.webp"},
    {"band": 800, "id": "lacquer", "label": "Лаковый колодец", "place_ru": "в лаке", "file": "shaft_800.webp"},
    {"band": 900, "id": "mercury", "label": "Ртуть", "place_ru": "у ртути", "file": "shaft_900.webp"},
    {"band": 1000, "id": "caramel", "label": "Карамель", "place_ru": "в карамели", "file": "shaft_1000.webp"},
    {"band": 1250, "id": "ink", "label": "Чернильный колодец", "place_ru": "в чернилах", "file": "shaft_1250.webp"},
    {"band": 1500, "id": "coral", "label": "Сухой коралл", "place_ru": "среди сухого коралла", "file": "shaft_1500.webp"},
    {"band": 1750, "id": "gears", "label": "Каменные шестерни", "place_ru": "среди шестерён", "file": "shaft_1750.webp"},
    {"band": 2000, "id": "pollen", "label": "Пыльца", "place_ru": "в пыльце", "file": "shaft_2000.webp"},
    {"band": 2500, "id": "enamel", "label": "Эмалевый колодец", "place_ru": "в эмали", "file": "shaft_2500.webp"},
    {"band": 3000, "id": "quiet", "label": "Пустой колодец", "place_ru": "в пустом колодце", "file": "shaft_3000.webp"},
)
SHAFT_BIOME_BY_BAND: dict[int, dict[str, Any]] = {int(b["band"]): b for b in SHAFT_BIOMES}


def shaft_band_for_depth(d: int) -> int:
    n = int(d or 0)
    if n <= 0:
        return int(SHAFT_BIOMES[0]["band"])
    for row in SHAFT_BIOMES:
        if n <= int(row["band"]):
            return int(row["band"])
    return int(SHAFT_BIOMES[-1]["band"])


def shaft_art_for_depth(d: int) -> dict[str, Any]:
    band = shaft_band_for_depth(d)
    row = SHAFT_BIOME_BY_BAND.get(band) or SHAFT_BIOMES[-1]
    return {
        "band": int(row["band"]),
        "id": str(row["id"]),
        "label": str(row["label"]),
        "place_ru": str(row.get("place_ru") or ""),
        "url": f"/static/game/delve/{row['file']}",
    }


def shaft_band_depths(d: int) -> list[int]:
    n = max(0, int(d or 0))
    if n <= 0:
        return list(range(1, 11))
    band = shaft_band_for_depth(n)
    bands = [int(b["band"]) for b in SHAFT_BIOMES]
    prev = 0
    for b in bands:
        if b >= band:
            break
        prev = b
    start = prev + 1 if prev else max(1, band - 9)
    end = band
    if end - start + 1 > 10:
        start = max(start, n - 6)
        return list(range(start, start + 10))
    return list(range(start, end + 1))

TITLES: tuple[tuple[int, str], ...] = (
    (10, "Спускалась"),
    (25, "Знает дно"),
    (50, "Держит фонарь"),
    (80, "Видела срыв"),
    (120, "Экспедиция помнит"),
)

COPY: dict[str, str] = {
    "tab": "Экспедиции",
    "onboard_1": "Они спускаются сами. Золото и опыт капают ей, забирать не нужно. Смотреть не обязательно.",
    "onboard_2": "Одна, две или три — только лица. Рекорд и пол одинаковые.",
    "start_cta": "Собрать отряд",
    "go_down": "Идти вниз",
    "faces_next": "Дальше — стойки",
    "reform": "Сменить лица",
    "tint_hint": "Можно подкрасить. Они уже идут.",
    "camp": "Сами пойдут.",
    "legacy": "Книгу закрыли. Они идут вниз. Рекорд глубины начнётся сейчас.",
    "locked": "Экспедиции откроются после первого закрытого данжа или с 5 уровня.",
    "need_waifu": "Сначала нужна основная вайфу.",
    "need_hire": "Сначала наймите наёмницу в таверне.",
    "tavern_cta": "В таверну",
    "sheet": "Статус",
    "open_column": "Открыть экспедиции",
    "profile_block": "Экспедиции",
    "record_label": "Рекорд",
    "now_label": "Сейчас",
    "title_label": "Титул",
    "unavailable": "Экспедиции недоступны",
    "boss_in": "До босса",
    "gold_party": "Золото отряда",
    "xp_party": "Опыт отряда",
    "gold_today": "Сегодня золота",
    "xp_today": "Сегодня опыта",
    "pq_power": "Сила",
    "pq_level": "Уровень",
    "pq_hp": "Здоровье",
    "pq_wallet": "золото",
    "pq_party": "Сила отряда",
    "pq_dmax": "Потолок",
}

HUD_STATUS: dict[str, str] = {
    "DESCENDING_FAST": "Спуск · несут",
    "DESCENDING_MID": "Спуск · вровень",
    "DESCENDING_HARD": "Спуск · тяжело",
    "ASCENDING": "Наверх",
    "SURFACE_REST": "Лагерь · сами пойдут",
}

NODE_LABEL_RU: dict[str, str] = {
    NODE_SURFACE: "Лагерь",
    NODE_BOSS: "Босс",
    NODE_BRANCH: "Вилка",
    NODE_LANDMARK: "Метка",
    NODE_REST: "Костёр",
    NODE_SHOP: "Лавка",
    NODE_TRAVERSE: "Переход",
    NODE_COMBAT: "Бой",
}

PALETTE_PLACE_RU: dict[str, str] = {
    "mushrooms": "грибной ход",
    "crystal": "кристальный ход",
    "coal": "угольный ход",
    "wet": "мокрый камень",
    "ash": "пепельный ход",
    "limestone": "известняк",
}

KICKER_BY_NODE: dict[str, str] = {
    NODE_TRAVERSE: "Спуск · {place}",
    NODE_COMBAT: "Бой · {place}",
    NODE_BOSS: "Босс · {place}",
    NODE_BRANCH: "Вилка · {place}",
    NODE_LANDMARK: "Метка · {place}",
    NODE_REST: "Привал · {place}",
    NODE_SHOP: "Лавка · {place}",
    NODE_SURFACE: "Лагерь",
}

JOURNAL_KIND_RU: dict[str, str] = {
    "landmark": "Метка на {d}",
    "shop": "Лавка на {d}",
    "sryv": "Срыв на {d}",
    "wipe": "Срыв спуска на {d}",
    "palette": "{palette}",
}

COMPANION_NAME_POOL: tuple[str, ...] = (
    "Ирида", "Сера", "Кайра", "Нора", "Лиса", "Вера", "Мира", "Аша",
    "Рея", "Таня", "Юна", "Эльза", "Соль", "Ника", "Дара", "Лена",
    "Оса", "Кира", "Фея", "Грей", "Руна", "Зоя", "Инга", "Палма",
    "Тесса", "Яра", "Сана", "Вита", "Эра", "Лада",
    "Айра", "Алма", "Арна", "Астра", "Бера", "Брига", "Веста", "Вирна",
    "Гала", "Гайя", "Дана", "Джуна", "Ева", "Ива", "Иона", "Калла",
    "Лара", "Луна", "Мара", "Морна", "Нева", "Орна", "Рива", "Роса",
    "Сива", "Сильва", "Тара", "Тора", "Уна", "Фрея", "Фрида", "Хана",
    "Хельма", "Эдна", "Юта", "Яна", "Берта", "Венда", "Герда", "Дина",
    "Ель", "Жара", "Зима", "Иска", "Лина", "Мела", "Нина", "Ольга",
    "Поля", "Рита", "Света", "Улья", "Флора", "Эмма", "Юля", "Ясна",
    "Агния", "Божена", "Влада", "Глаша", "Динара", "Есения", "Ждана",
    "Заря", "Изольда", "Лайма", "Милана", "Надя", "Оксана", "Рада",
    "Слава", "Таиса", "Устинья", "Фаина", "Харита", "Элина", "Ядвига",
    "Аврора", "Бригитта", "Волна", "Гора", "Дрозд", "Искра", "Крапива",
    "Ладана", "Морок", "Нея", "Острога", "Пепел", "Роща", "Степь",
    "Тень", "Уголь", "Хвойка", "Цвета", "Шипка", "Янтарь",
)

# One short sentence. Subject = companion name via {name}.
PHRASES: dict[str, tuple[str, ...]] = {
    NODE_COMBAT: (
        "{name} рубит споры.",
        "{name} бьёт коротко.",
        "{name} не отступает.",
        "{name} держит ритм.",
        "{name} режет тишину.",
        "{name} стоит в ударе.",
    ),
    NODE_TRAVERSE: (
        "{name} идёт дальше.",
        "{name} считает шаги.",
        "{name} молчит и идёт.",
        "{name} не оглядывается.",
        "{name} ведёт вниз.",
        "{name} знает камень.",
    ),
    NODE_REST: (
        "{name} ждёт, пока капнет.",
        "{name} греет руки.",
        "{name} сидит у угля.",
        "{name} молчит у огня.",
    ),
    NODE_SHOP: (
        "{name} купила безделушку.",
        "{name} не торгуется.",
        "{name} кивает лавке.",
        "{name} уходит с мелочью.",
    ),
    NODE_BRANCH: (
        "{name} не сворачивает.",
        "{name} уже выбрала.",
        "{name} идёт своим рукавом.",
        "{name} не спрашивает.",
    ),
    NODE_LANDMARK: (
        "{name} ставит метку.",
        "{name} трогает камень.",
        "{name} запоминает место.",
        "{name} кивает вешке.",
    ),
    NODE_BOSS: (
        "{name} смотрит в глаза.",
        "{name} не кланяется.",
        "{name} держит строй.",
        "{name} бьёт последней.",
    ),
    NODE_SURFACE: (
        "{name} сидит у костра.",
        "{name} чинит ремень.",
        "{name} снова пойдёт.",
        "{name} не зовёт.",
    ),
}

PALETTE_FLAVOR: dict[str, tuple[str, ...]] = {
    "mushrooms": ("Споры липнут к сапогу.", "Воздух сладкий и тяжёлый."),
    "crystal": ("Свет режет глаз.", "Камень звенит под ногой."),
    "coal": ("Жар стоит в горле.", "Сажа на пальцах."),
    "wet": ("Каплет за ворот.", "Стена холодная."),
    "ash": ("Пыль садится на губы.", "Шаг глухой."),
    "limestone": ("Мел скрипит.", "Белый край на перчатке."),
}


def gold_cap_day(*, gold_of_chat_cap: float | None = None, chat_gold_cap: int | None = None) -> int:
    cap = int(chat_gold_cap if chat_gold_cap is not None else CHAT_GOLD_CAP_DEFAULT)
    rate = float(gold_of_chat_cap if gold_of_chat_cap is not None else GOLD_OF_CHAT_CAP_DEFAULT)
    return max(0, int(rate * cap))


def typical_solo_xp_day(ov_level: int) -> int:
    nxt = max(2, int(ov_level or 1) + 1)
    return max(0, int(SOLO_XP_DAY_K * calculate_experience_for_level(nxt)))


def xp_cap_day(ov_level: int, *, frac: float | None = None) -> int:
    f = float(frac if frac is not None else XP_OF_SOLO_DAY_DEFAULT)
    return max(0, int(f * typical_solo_xp_day(ov_level)))


def gold_rate_per_sec(cap: int) -> float:
    return float(cap) / float(DAY_SEC)


def xp_rate_per_sec(cap: int) -> float:
    return float(cap) / float(DAY_SEC)


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def msk_today(now: datetime | None = None) -> str:
    now = _aware(now or datetime.now(timezone.utc))
    return now.astimezone(MSK).date().isoformat()


def msk_day_start(now: datetime) -> datetime:
    local = _aware(now).astimezone(MSK)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc)


def next_msk_midnight(now: datetime) -> datetime:
    return msk_day_start(now) + timedelta(days=1)


def hours_in_column(t_origin: datetime, now: datetime) -> float:
    return max(0.0, (_aware(now) - _aware(t_origin)).total_seconds() / 3600.0)


def d_ceiling(hours: float, ov_level: int) -> float:
    a = max(0.0, float(hours))
    lvl = max(1, int(ov_level or 1))
    base = D0 * (1.0 + ALPHA * math.log(1.0 + a)) * (1.0 + 0.03 * math.sqrt(lvl))
    tail = CEILING_TAIL_K * (max(0.0, a - CEILING_TAIL_HOURS) ** CEILING_TAIL_EXP)
    return base + tail


def period_parts(ceil: float) -> tuple[float, float, float]:
    c = max(1.0, float(ceil))
    t_down = T0_SEC * math.log(1.0 + c)
    t_rest = 50.0 + 10.0 * math.log(1.0 + c)
    return t_down, T_UP_SEC, t_rest


def sawtooth(*, t_origin: datetime, now: datetime, ov_level: int, d_max: int | None = None) -> dict[str, Any]:
    now = _aware(now)
    origin = _aware(t_origin)
    hours = hours_in_column(origin, now)
    ceil = d_ceiling(hours, ov_level)
    if d_max is not None:
        ceil = float(max(1, int(d_max)))
    t_down, t_up, t_rest = period_parts(ceil)
    period = t_down + t_up + t_rest
    elapsed = max(0.0, (now - origin).total_seconds())
    phase = elapsed % period if period > 0 else 0.0
    if phase < t_down:
        u = phase / t_down if t_down > 0 else 1.0
        depth = 1.0 + (ceil - 1.0) * (u**DEPTH_EXP)
        state = STATE_DESCENDING
        if u < 0.35:
            status_key = "DESCENDING_FAST"
            pace = "fast"
        elif u < 0.75:
            status_key = "DESCENDING_MID"
            pace = "mid"
        else:
            status_key = "DESCENDING_HARD"
            pace = "hard"
    elif phase < t_down + t_up:
        v = (phase - t_down) / t_up if t_up > 0 else 1.0
        depth = ceil * (1.0 - v)
        state = STATE_ASCENDING
        status_key = "ASCENDING"
        pace = "up"
        u = 1.0
    else:
        depth = 0.0
        state = STATE_REST
        status_key = "SURFACE_REST"
        pace = "camp"
        u = 0.0
    d_floor = max(0, int(math.floor(depth)))
    implied = implied_record(elapsed_sec=elapsed, depth=depth, ceil=ceil, t_down=t_down)
    strain = 0.0
    if state == STATE_DESCENDING and ceil > 0:
        strain = min(1.0, max(0.0, depth / ceil))
    return {
        "hours": hours,
        "d_ceiling": ceil,
        "depth": depth,
        "d": d_floor,
        "state": state,
        "status_key": status_key,
        "status": HUD_STATUS[status_key],
        "pace": pace,
        "t_down": t_down,
        "t_up": t_up,
        "t_rest": t_rest,
        "period": period,
        "phase": phase,
        "elapsed_sec": elapsed,
        "implied_record": implied,
        "strain": strain,
        "u": u if state == STATE_DESCENDING else 0.0,
    }


def implied_record(*, elapsed_sec: float, depth: float, ceil: float, t_down: float) -> int:
    if elapsed_sec >= t_down:
        return max(0, int(math.floor(ceil)))
    return max(0, int(math.floor(depth)))


def is_landmark(d: int) -> bool:
    if int(d) <= 0:
        return False
    return int(d) % 100 in _BASE_LANDMARKS


def spine_type(d: int, ceil: float) -> str:
    n = int(d)
    if n <= 0:
        return NODE_SURFACE
    if n % 10 == 0:
        return NODE_BOSS
    if n % 5 == 0:
        return NODE_BRANCH
    if is_landmark(n):
        return NODE_LANDMARK
    if n % 8 == 6:
        return NODE_REST
    if n % 12 == 4:
        return NODE_SHOP
    if ceil > 0 and n < 0.35 * ceil:
        return NODE_TRAVERSE
    return NODE_COMBAT


def title_for_record(record: int) -> str | None:
    label = None
    for need, name in TITLES:
        if int(record) >= int(need):
            label = name
    return label


def title_id_for_record(record: int) -> int:
    tid = 0
    for i, (need, _name) in enumerate(TITLES, start=1):
        if int(record) >= int(need):
            tid = i
    return tid


def palette_at(index: int) -> dict[str, str]:
    return PALETTES[int(index) % len(PALETTES)]


def seed_palette_id(spine_seed: int) -> str:
    return PALETTE_IDS[int(spine_seed) % len(PALETTE_IDS)]


def instinct_sleeve(tempers: Sequence[str]) -> int:
    curiosity = sum(1 for t in tempers if t == "curiosity")
    temper_n = sum(1 for t in tempers if t == "temper")
    stay = sum(1 for t in tempers if t == "stay")
    w0 = 1.0 + 0.35 * curiosity + 0.20 * temper_n + 0.10 * stay
    w1 = 1.0 + 0.35 * stay + 0.20 * curiosity
    return 0 if w0 >= w1 else 1


def branch_sleeves(committed_id: str, spine_seed: int, d: int) -> tuple[str, str]:
    base = PALETTE_IDS.index(committed_id) if committed_id in PALETTE_IDS else 0
    other = (base + 1 + (int(spine_seed) + int(d)) % 5) % len(PALETTE_IDS)
    if other == base:
        other = (base + 1) % len(PALETTE_IDS)
    return PALETTE_IDS[base], PALETTE_IDS[other]


def phrase_for(*, node: str, palette_id: str, name: str, spine_seed: int, d: int) -> str:
    pool = PHRASES.get(node) or PHRASES[NODE_TRAVERSE]
    rng = random.Random(int(hashlib.sha256(f"delve-line:{spine_seed}:{d}:{node}".encode()).hexdigest()[:16], 16))
    text = rng.choice(pool).format(name=name or "Она")
    return text


def frame_kicker(node: str, palette_id: str) -> str:
    place = PALETTE_PLACE_RU.get(palette_id, "камне")
    tmpl = KICKER_BY_NODE.get(node, "Идут по {place}")
    if "{place}" not in tmpl:
        return tmpl
    return tmpl.format(place=place)


def journal_stamp_label(kind: str, d: int, palette_id: str) -> str:
    pal = PALETTE_BY_ID.get(palette_id, {}).get("label", palette_id or "")
    tmpl = JOURNAL_KIND_RU.get(str(kind or ""), "{kind}")
    return tmpl.format(d=int(d or 0), palette=pal, kind=kind)


def split_even(total: int, n: int) -> list[int]:
    """Split a grant across n faces. Sum equals total. 1=3 economy stays party-flat."""
    if n <= 0 or total <= 0:
        return [0] * max(0, int(n))
    q, r = divmod(int(total), int(n))
    return [q + (1 if i < r else 0) for i in range(int(n))]


def split_weighted(total: int, weights: Sequence[int]) -> list[int]:
    """Split a grant by positive weights. Sum equals total."""
    n = len(weights)
    if n <= 0:
        return []
    if total <= 0:
        return [0] * n
    cleaned = [max(1, int(w or 0)) for w in weights]
    s = sum(cleaned)
    raw = [int(total) * w / s for w in cleaned]
    floors = [int(x) for x in raw]
    rem = int(total) - sum(floors)
    order = sorted(range(n), key=lambda i: (raw[i] - floors[i], -i), reverse=True)
    for i in order[: max(0, rem)]:
        floors[i] += 1
    return floors


def days_in_party(joined_at: datetime | None, now: datetime | None = None) -> int:
    if joined_at is None:
        return 0
    now = _aware(now or datetime.now(timezone.utc))
    delta = now - _aware(joined_at)
    return max(0, int(delta.total_seconds() // 86400))


def floor_pct(granted_today: int, cap: int) -> int:
    if cap <= 0:
        return 100
    return max(0, min(100, int(round(100.0 * int(granted_today) / int(cap)))))


def walk_capped_grant(
    last_ts: datetime,
    now: datetime,
    *,
    rate: float,
    cap: int,
    day_key: str | None,
    granted_today: int,
) -> tuple[int, str, int]:
    """O(days) bucket walk. Daily owed = min(cap, int(rate * seconds_into_that_day))."""
    now = _aware(now)
    cursor = _aware(last_ts)
    if cursor >= now or cap <= 0 or rate <= 0:
        key = day_key or msk_today(now)
        return 0, key, max(0, int(granted_today))
    total = 0
    today = str(day_key or msk_today(cursor))
    bucket = max(0, int(granted_today))
    steps = 0
    while cursor < now and steps < 400:
        steps += 1
        key = msk_today(cursor)
        if key != today:
            today = key
            bucket = 0
        start = msk_day_start(cursor)
        owed_at_cursor = min(int(cap), int(rate * max(0.0, (cursor - start).total_seconds())))
        if bucket < owed_at_cursor:
            bucket = owed_at_cursor
        day_end = next_msk_midnight(cursor)
        chunk_end = now if day_end > now else day_end
        sec_into = max(0.0, (chunk_end - start).total_seconds())
        owed = min(int(cap), int(rate * sec_into))
        chunk = max(0, owed - bucket)
        bucket += chunk
        total += chunk
        cursor = chunk_end
    if msk_today(now) != today:
        today = msk_today(now)
        bucket = 0
    return total, today, bucket


def journal_stamps_for_record(record: int, palette_id: str, *, sryv: bool) -> list[dict[str, Any]]:
    """Unlock collection from the record, not by replaying ticks."""
    stamps: list[dict[str, Any]] = []
    rec = max(0, int(record))
    seen: set[tuple[str, int]] = set()
    block = 0
    while block <= rec and len(stamps) < 80:
        for base in _BASE_LANDMARKS:
            d = block + int(base)
            if 1 <= d <= rec:
                key = ("landmark", d)
                if key not in seen:
                    seen.add(key)
                    stamps.append({"kind": "landmark", "d": d, "palette": palette_id})
        block += 100
    d = 4
    while d <= rec and len(stamps) < 80:
        key = ("shop", d)
        if key not in seen:
            seen.add(key)
            stamps.append({"kind": "shop", "d": d, "palette": palette_id})
        d += 12
    if sryv:
        stamps.append({"kind": "sryv", "d": rec, "palette": palette_id})
    return stamps


def merge_journal(existing: list | dict | None, incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(existing, list):
        rows = [x for x in existing if isinstance(x, dict)]
    have = {(str(x.get("kind")), int(x.get("d") or 0)) for x in rows}
    for item in incoming:
        key = (str(item.get("kind")), int(item.get("d") or 0))
        if key in have:
            continue
        have.add(key)
        rows.append(item)
    return rows[:120]


def pick_companion_name(
    player_id: int,
    slot: int,
    *,
    exclude: Sequence[str] = (),
    salt: object = "",
) -> str:
    taken = {str(x).strip() for x in exclude}
    digest = hashlib.sha256(
        f"delve-name:{int(player_id)}:{int(slot)}:{salt}".encode()
    ).hexdigest()[:16]
    rng = random.Random(int(digest, 16))
    pool = [n for n in COMPANION_NAME_POOL if n not in taken] or list(COMPANION_NAME_POOL)
    return rng.choice(pool)


_PERSON_NAME_RE = re.compile(r"[А-ЯЁ][а-яё]{1,23}(?:-[А-ЯЁ][а-яё]{1,23})?")
_KEEP_WORDS = frozenset(
    {
        "А",
        "И",
        "Но",
        "Да",
        "Нет",
        "В",
        "Во",
        "На",
        "По",
        "У",
        "К",
        "Ко",
        "С",
        "Со",
        "Из",
        "За",
        "От",
        "До",
        "При",
        "Про",
        "О",
        "Об",
        "Обо",
        "Над",
        "Под",
        "Перед",
        "Через",
        "Между",
        "Для",
        "Без",
        "Она",
        "Они",
        "Он",
        "Её",
        "Ее",
        "Их",
        "Ей",
        "Им",
        "Отряд",
        "Спутница",
        "Наёмница",
        "Наемница",
        "Хозяйка",
        "Там",
        "Тут",
        "Здесь",
        "Потом",
        "Снова",
        "Опять",
        "Дальше",
        "Впереди",
        "Сзади",
        "Тихо",
        "Громко",
        "Глубоко",
        "Вдруг",
        "Чуть",
        "Едва",
        "Уже",
        "Ещё",
        "Еще",
        "Пора",
        "Пока",
        "Тогда",
        "Камень",
        "Коридор",
        "Шахта",
        "Лавка",
        "Метка",
        "Босс",
        "Вилка",
        "Привал",
        "Лагерь",
        "Вода",
        "Тишина",
        "Темнота",
        "Пыль",
        "Кровь",
        "Рана",
        "Паутина",
        "Стена",
        "Потолок",
        "Тропа",
        "Ход",
        "Лёд",
        "Лед",
        "Тень",
        "Бездна",
        "Мокрое",
        "Грибы",
        "Кристалл",
        "Уголь",
        "Пепел",
        "Кости",
        "Ржавчина",
        "Соль",
        "Архив",
        "Смола",
        "Фарфор",
        "Медянка",
        "Сукно",
        "Воск",
        "Лак",
        "Чернила",
        "Зубья",
        "Эмаль",
        "Тишина",
    }
    | {str(p["label"]) for p in PALETTES}
    | {str(b["label"]) for b in SHAFT_BIOMES}
    | {w for label in [str(p["label"]) for p in PALETTES] + [str(b["label"]) for b in SHAFT_BIOMES] for w in label.split()}
)


def replace_companion_name(text: str, old: str, new: str) -> str:
    """Swap one mercenary name for another; word boundaries only."""
    src = (old or "").strip()
    dst = (new or "").strip()
    if not text or not src or not dst or src == dst:
        return text
    return re.sub(
        rf"(?<![А-Яа-яЁёA-Za-z]){re.escape(src)}(?![А-Яа-яЁёA-Za-z])",
        dst,
        text,
    )


def enforce_squad_names(text: str, names: Sequence[str], *, face: str | None = None) -> str:
    """Keep only current mercenary names in a flavor line. Invented pool names go out."""
    raw = (text or "").strip()
    squad = [str(n).strip() for n in names if str(n).strip()]
    lead = (face or (squad[0] if squad else "")).strip()
    if not raw or not lead:
        return raw
    squad_fold = {n.casefold(): n for n in squad}
    pool = set(COMPANION_NAME_POOL)
    extras = squad[1:]
    extra_i = 0

    def _sentence_start(idx: int) -> bool:
        if idx <= 0:
            return True
        prev = raw[:idx].rstrip()
        return not prev or prev.endswith((".", "!", "?", "…"))

    def _sub(match: re.Match[str]) -> str:
        nonlocal extra_i
        word = match.group(0)
        canon = squad_fold.get(word.casefold())
        if canon:
            return canon
        if word in _KEEP_WORDS:
            return word
        invented = word in pool
        if (
            not invented
            and _sentence_start(match.start())
            and len(word) >= 3
            and word[-1] in "аяАЯ"
        ):
            invented = True
        if not invented:
            return word
        if _sentence_start(match.start()):
            return lead
        if extra_i < len(extras):
            out = extras[extra_i]
            extra_i += 1
            return out
        return lead

    out = _PERSON_NAME_RE.sub(_sub, raw)
    if not any(n in out for n in squad):
        found = _PERSON_NAME_RE.search(out)
        if found and found.group(0) not in _KEEP_WORDS:
            out = out[: found.start()] + lead + out[found.end() :]
        else:
            pron = re.match(r"^(Она|Они)(?![А-Яа-яЁё])", out)
            if pron:
                out = lead + out[pron.end() :]
            else:
                rest = out
                if rest[:1].isupper() and rest[1:2].islower():
                    rest = rest[0].lower() + rest[1:]
                out = f"{lead} {rest}".strip()
    return out


def format_waifu_html(name: str | None) -> str:
    label = (name or "").strip().lstrip("@") or "—"
    return f"<b>{html.escape(label)}</b>"


def format_waifu_plain(name: str | None) -> str:
    return (name or "").strip().lstrip("@") or "—"


def template_portrait_url(stance: str) -> str:
    sid = stance if stance in STANCES else "guide"
    return f"/static/game/delve/templates/{sid}.webp"


def portrait_public_url(player_id: int, slot: int) -> str:
    """Static webp path. <img> cannot send Telegram init headers to /api/delve/portraits."""
    return f"/static/{portrait_relpath(int(player_id), int(slot))}"


def portrait_relpath(player_id: int, slot: int) -> str:
    return f"game/delve/portraits/{int(player_id)}_{int(slot)}.webp"


def reform_ready(last_reform_at: datetime | None, now: datetime | None = None) -> bool:
    if last_reform_at is None:
        return True
    now = _aware(now or datetime.now(timezone.utc))
    return (_aware(now) - _aware(last_reform_at)) >= timedelta(days=REFORM_CD_DAYS)


def viewport_depths(d: int, *, n: int = VIEWPORT_NODES) -> list[int]:
    """Current node near the lower third of a 14-high strip."""
    half_below = max(1, n // 3)
    start = max(0, int(d) - (n - half_below - 1))
    return list(range(start, start + n))
