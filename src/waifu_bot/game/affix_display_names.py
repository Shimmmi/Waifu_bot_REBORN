"""Russian display names for item affixes (prefix/suffix), shared by ItemService and library API."""

from __future__ import annotations

import re

_PREFIX_NAME_BY_STAT: dict[str, dict[tuple[int, int], str]] = {
    # tier ranges -> RU name (masc form; UI inflects by gender later)
    "strength": {(1, 2): "Мощный", (3, 4): "Грозный", (5, 6): "Сокрушительный", (7, 8): "Титанический", (9, 10): "Божественный"},
    "agility": {(1, 2): "Быстрый", (3, 4): "Стремительный", (5, 6): "Молниеносный", (7, 8): "Неуловимый", (9, 10): "Эфирный"},
    "intelligence": {(1, 2): "Мудрый", (3, 4): "Проницательный", (5, 6): "Архимудрый", (7, 8): "Просветлённый", (9, 10): "Всеведущий"},
    "endurance": {(1, 2): "Крепкий", (3, 4): "Несокрушимый", (5, 6): "Непробиваемый", (7, 8): "Твердыня", (9, 10): "Непокорный"},
    "charm": {(1, 2): "Очаровательный", (3, 4): "Утончённый", (5, 6): "Неотразимый", (7, 8): "Чарующий", (9, 10): "Великолепный"},
    "luck": {(1, 2): "Удачливый", (3, 4): "Фартовый", (5, 6): "Счастливый", (7, 8): "Избранный", (9, 10): "Благословенный"},
    "melee_damage_flat": {
        (1, 2): "Рубящий",
        (3, 4): "Дробящий",
        (5, 6): "Крушащий",
        (7, 8): "Карающий",
        (9, 10): "Безжалостный",
    },
    "ranged_damage_flat": {
        (1, 2): "Меткий",
        (3, 4): "Снайперский",
        (5, 6): "Дальнобойный",
        (7, 8): "Звёздный",
        (9, 10): "Небесный",
    },
    "magic_damage_flat": {
        (1, 2): "Зачарованный",
        (3, 4): "Мистический",
        (5, 6): "Арканный",
        (7, 8): "Этерический",
        (9, 10): "Первозданный",
    },
    "damage_flat": {
        (1, 2): "Острый",
        (3, 4): "Яростный",
        (5, 6): "Яростный",
        (7, 8): "Сокрушительный",
        (9, 10): "Легендарный",
    },
    "damage_percent": {
        (1, 2): "Усиленный",
        (3, 4): "Могучий",
        (5, 6): "Грозный",
        (7, 8): "Разящий",
        (9, 10): "Апокалиптический",
    },
}

# Род. пл. для суффиксов s_monster_*_flat / *_pct (если нет отдельной строки в _SUFFIX_NAME_BY_FAMILY_ID)
_MONSTER_FAMILY_GENITIVE_RU: dict[str, str] = {
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

_SUFFIX_NAME_BY_FAMILY_ID: dict[str, dict[int, str]] = {
    # family_id (string key) -> affix_tier -> RU name
    "s_monster_undead_slayer": {2: "убийцы нежити", 4: "карателя нежити", 6: "истребителя нежити", 8: "уничтожителя нежити", 10: "супер‑пупер убивателя нежити"},
    "s_media_text": {2: "рассказчика", 4: "писателя", 6: "поэта", 8: "барда", 10: "легендарного барда"},
    "s_media_sticker": {2: "стикерщика", 4: "эмодзи", 6: "мемолога", 8: "стикерного мастера", 10: "короля стикеров"},
    "s_media_photo": {2: "фотографа", 4: "мастера фото", 6: "художника кадра", 8: "виртуоза кадра", 10: "легенды кадра"},
    "s_media_gif": {2: "гифмейкера", 4: "аниматора", 6: "цикличности", 8: "петли судьбы", 10: "вечного гифа"},
    "s_media_audio": {2: "диджея", 4: "звукорежиссёра", 6: "резонанса", 8: "саундтрека", 10: "симфонии"},
    "s_media_voice": {2: "оратора", 4: "говоруна", 6: "эхо", 8: "голоса бездны", 10: "пророчества"},
    "s_media_video": {2: "монтажёра", 4: "режиссёра", 6: "киношника", 8: "стримера", 10: "кинолегенды"},
    "s_media_link": {2: "линкера", 4: "мастера ссылок", 6: "гиперссылки", 8: "веба", 10: "интернета"},
    "s_dmg_melee": {2: "ближнего боя", 4: "рукопашной резни", 6: "тесаков", 8: "титанов", 10: "бездны ударов"},
    "s_dmg_ranged": {2: "дальнего боя", 4: "меткости", 6: "дождя стрел", 8: "ветра", 10: "небесного лука"},
    "s_dmg_magic": {2: "чар", 4: "заклинаний", 6: "арканы", 8: "бездны маны", 10: "апокалипсиса магии"},
    "s_merchant_cut": {
        1: "купца",
        2: "торгаша",
        3: "базара",
        4: "лотка",
        5: "скупки",
        6: "выгоды",
        7: "расчёта",
        8: "контракта",
        9: "империи торговли",
        10: "золотого ключика",
    },
    "s_sec_crit_chance_pct": {
        1: "остроты",
        2: "точности",
        3: "пробития",
        4: "разрыва",
        5: "кары",
        6: "расплаты",
        7: "приговора",
        8: "бури",
        9: "рока",
        10: "апокалипсиса",
    },
    "s_sec_evade_pct": {
        1: "уворота",
        2: "стремительности",
        3: "лёгкости",
        4: "пустоты",
        5: "иллюзии",
        6: "мглы",
        7: "тени",
        8: "призрака",
        9: "ветра",
        10: "невидимости",
    },
    "s_sec_dmg_reduce_pct": {
        1: "стойкости",
        2: "плиты",
        3: "бастиона",
        4: "стражи",
        5: "барьера",
        6: "осады",
        7: "непоколебимости",
        8: "крепости",
        9: "эгиды",
        10: "небесной стены",
    },
    "s_sec_hp_max_pct": {
        1: "жизни",
        2: "крови",
        3: "пульса",
        4: "живучести",
        5: "витальности",
        6: "долголетия",
        7: "бессмертия",
        8: "родословной",
        9: "титана",
        10: "вечности",
    },
    "s_sec_exp_bonus_pct": {
        1: "учёности",
        2: "озарения",
        3: "тайн",
        4: "знаний",
        5: "архива",
        6: "прозрения",
        7: "звёзд",
        8: "бездны",
        9: "пророчества",
        10: "творения",
    },
    "s_sec_gold_bonus_pct": {
        1: "купца",
        2: "сделки",
        3: "монет",
        4: "удачи",
        5: "фортуны",
        6: "счёта",
        7: "казны",
        8: "богатства",
        9: "провидца",
        10: "вселенной",
    },
    "s_sec_magic_find_pct": {
        1: "находки",
        2: "добычи",
        3: "охоты",
        4: "сокровищ",
        5: "артефактов",
        6: "легенд",
        7: "мифов",
        8: "редкости",
        9: "эпоса",
        10: "мифического фарма",
    },
    "s_sell_high": {
        1: "скупщика",
        2: "выкупа",
        3: "ломбарда",
        4: "торга",
        5: "прибыли",
        6: "расчёта",
        7: "рынка",
        8: "базара",
        9: "лотка",
        10: "империи скупки",
    },
    "s_tavern_favor": {
        1: "таверны",
        2: "кружки",
        3: "трактира",
        4: "постоя",
        5: "ночлега",
        6: "очага",
        7: "застолья",
        8: "кубка",
        9: "хмеля",
        10: "вечного пира",
    },
}

_PASSIVE_LEVEL_ADD_PREFIX: dict[tuple[int, int], str] = {
    (1, 3): "Наставнический",
    (4, 6): "Мастерский",
    (7, 8): "Просветляющий",
    (9, 10): "Первозданный",
}

_PASSIVE_LEVEL_ADD_SUFFIX: dict[int, str] = {
    1: "ученика",
    2: "подмастерья",
    3: "адепта",
    4: "знатока",
    5: "эксперта",
    6: "мастера",
    7: "наставника",
    8: "архимастера",
    9: "парадигмы",
    10: "бесконечности",
}

# Аффиксы к конкретному узлу пассива сильно поднимают ilvl (цена магазина / base_value).
_PASSIVE_NODE_AFFIX_LEVEL_DELTA_MULT = 5

_TEMPLATE_FRACTION_SECONDARIES: frozenset[str] = frozenset(
    {
        "crit_chance_pct",
        "evade_pct",
        "dmg_reduce_pct",
        "hp_max_pct",
        "exp_bonus_pct",
        "gold_bonus_pct",
        "magic_find_pct",
    }
)

# Префиксы для вторичных effect_key (совпадают с суффиксными семействами по числовому ключу).
_SECONDARY_PREFIX_NAMES: dict[str, dict[tuple[int, int], str]] = {
    "crit_chance_pct": {
        (1, 2): "Заострённый",
        (3, 4): "Критичный",
        (5, 6): "Жестокий",
        (7, 8): "Убийственный",
        (9, 10): "Апокалиптический",
    },
    "evade_pct": {
        (1, 2): "Проворный",
        (3, 4): "Уклончивый",
        (5, 6): "Неуловимый",
        (7, 8): "Фантомный",
        (9, 10): "Эфирный",
    },
    "dmg_reduce_pct": {
        (1, 2): "Крепкий",
        (3, 4): "Бронированный",
        (5, 6): "Несокрушимый",
        (7, 8): "Непробиваемый",
        (9, 10): "Непокорный",
    },
    "hp_max_pct": {
        (1, 2): "Кровный",
        (3, 4): "Живучий",
        (5, 6): "Стойкий",
        (7, 8): "Титанический",
        (9, 10): "Бессмертный",
    },
    "exp_bonus_pct": {
        (1, 2): "Любознательный",
        (3, 4): "Проницательный",
        (5, 6): "Мудрый",
        (7, 8): "Просветлённый",
        (9, 10): "Всеведущий",
    },
    "gold_bonus_pct": {
        (1, 2): "Богатый",
        (3, 4): "Щедрый",
        (5, 6): "Фартовый",
        (7, 8): "Счастливый",
        (9, 10): "Золотой",
    },
    "magic_find_pct": {
        (1, 2): "Искательный",
        (3, 4): "Коллекционный",
        (5, 6): "Реликтовый",
        (7, 8): "Мифический",
        (9, 10): "Сокровищный",
    },
    "merchant_discount_flat": {
        (1, 2): "Торговый",
        (3, 4): "Скупой",
        (5, 6): "Выгодный",
        (7, 8): "Расчётливый",
        (9, 10): "Купеческий",
    },
    "merchant_discount_percent": {
        (1, 2): "Торговый",
        (3, 4): "Скупой",
        (5, 6): "Выгодный",
        (7, 8): "Расчётливый",
        (9, 10): "Купеческий",
    },
    "sell_price_bonus_percent": {
        (1, 2): "Выгодный",
        (3, 4): "Скупочный",
        (5, 6): "Перекупский",
        (7, 8): "Расчётливый",
        (9, 10): "Золотой",
    },
    "tavern_discount_percent": {
        (1, 2): "Гостеприимный",
        (3, 4): "Трактирный",
        (5, 6): "Постоялый",
        (7, 8): "Кружечный",
        (9, 10): "Ночующий",
    },
    "media_damage_text_percent": {
        (1, 2): "Болтливый",
        (3, 4): "Словесный",
        (5, 6): "Красноречивый",
        (7, 8): "Ораторский",
        (9, 10): "Легендарный",
    },
    "media_damage_sticker_percent": {
        (1, 2): "Стикерный",
        (3, 4): "Эмодзи",
        (5, 6): "Мемный",
        (7, 8): "Вирусный",
        (9, 10): "Стикерхолик",
    },
    "media_damage_photo_percent": {
        (1, 2): "Снимающий",
        (3, 4): "Фотогеничный",
        (5, 6): "Объективный",
        (7, 8): "Кадровый",
        (9, 10): "Шедевральный",
    },
    "media_damage_gif_percent": {
        (1, 2): "Гифующий",
        (3, 4): "Цикличный",
        (5, 6): "Анимированный",
        (7, 8): "Петлевой",
        (9, 10): "Бесконечный",
    },
    "media_damage_audio_percent": {
        (1, 2): "Звучащий",
        (3, 4): "Аудиальный",
        (5, 6): "Резонирующий",
        (7, 8): "Саундтрековый",
        (9, 10): "Симфонический",
    },
    "media_damage_voice_percent": {
        (1, 2): "Голосистый",
        (3, 4): "Говорящий",
        (5, 6): "Ораторский",
        (7, 8): "Эхо",
        (9, 10): "Пророческий",
    },
    "media_damage_video_percent": {
        (1, 2): "Видео",
        (3, 4): "Киношный",
        (5, 6): "Стримовый",
        (7, 8): "Режиссёрский",
        (9, 10): "Кинолегендарный",
    },
    "media_damage_link_percent": {
        (1, 2): "Линкованный",
        (3, 4): "Гиперссылочный",
        (5, 6): "Вебовый",
        (7, 8): "Ссылочный",
        (9, 10): "Интернетный",
    },
}


_FAMILY_ID_RE = re.compile(r"^(p|s)_[a-z0-9_]+$", re.IGNORECASE)
_EFFECT_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$", re.IGNORECASE)


def _is_raw_affix_name(
    name: str, *, effect_key: str | None = None, family_id: str | None = None
) -> bool:
    """True when name is an untranslated effect_key or family_id placeholder."""
    s = str(name or "").strip()
    if not s:
        return False
    if family_id and s == family_id:
        return True
    if effect_key and s.lower() == str(effect_key).lower():
        return True
    if _FAMILY_ID_RE.match(s):
        return True
    if _EFFECT_KEY_RE.match(s):
        return True
    if re.search(r"[A-Za-z_]", s) and "_" in s:
        return True
    return False


def _resolve_prefix_name_ru_legacy(stat: str, affix_tier: int) -> str:
    st = str(stat or "")
    low = st.lower().replace("audioo", "audio").replace("magii", "magic")
    if low.startswith("passive_node_level_add:") or low.startswith(
        "passive_branch_level_add:"
    ):
        tr = int(affix_tier)
        for (a, b), name in _PASSIVE_LEVEL_ADD_PREFIX.items():
            if a <= tr <= b:
                return name
        return "Наставнический"
    if low == "passive_all_nodes_level_add":
        tr = int(affix_tier)
        for (a, b), name in _PASSIVE_LEVEL_ADD_PREFIX.items():
            if a <= tr <= b:
                return name
        return "Наставнический"
    sec_ranges = _SECONDARY_PREFIX_NAMES.get(low) or {}
    for (a, b), name in sec_ranges.items():
        if a <= int(affix_tier) <= b:
            return name
    ranges = _PREFIX_NAME_BY_STAT.get(low) or {}
    for (a, b), name in ranges.items():
        if a <= affix_tier <= b:
            return name
    return (stat or "").capitalize() or "Префикс"


def resolve_prefix_name_ru(
    stat: str, affix_tier: int, *, family_id: str | None = None
) -> str:
    from waifu_bot.game.affix_display_names_llm import lookup_affix_display_name_ru

    cached = lookup_affix_display_name_ru(family_id, affix_tier)
    if cached and not _is_raw_affix_name(cached, effect_key=stat, family_id=family_id):
        return cached
    return _resolve_prefix_name_ru_legacy(stat, affix_tier)


def _resolve_suffix_name_ru_legacy(family_key: str, affix_tier: int) -> str:
    fk = str(family_key or "")
    if fk.startswith("s_passive_lvl_") or fk.startswith("s_passive_branch_"):
        return _PASSIVE_LEVEL_ADD_SUFFIX.get(int(affix_tier), "наставления")
    if fk == "s_passive_all":
        return _PASSIVE_LEVEL_ADD_SUFFIX.get(int(affix_tier), "наставления")
    per_tier = _SUFFIX_NAME_BY_FAMILY_ID.get(family_key) or {}
    if per_tier:
        t = int(affix_tier)
        if t in per_tier:
            return per_tier[t]
        keys = sorted(int(k) for k in per_tier)
        for k in reversed(keys):
            if k <= t:
                return per_tier[k]
        return per_tier[keys[0]]
    mm = re.match(r"^s_monster_(\w+)_(flat|pct)$", fk, re.IGNORECASE)
    if mm:
        fam = mm.group(1).lower()
        return _MONSTER_FAMILY_GENITIVE_RU.get(fam, fam)
    return family_key


def resolve_suffix_name_ru(family_key: str, affix_tier: int) -> str:
    from waifu_bot.game.affix_display_names_llm import lookup_affix_display_name_ru

    cached = lookup_affix_display_name_ru(family_key, affix_tier)
    if cached and not _is_raw_affix_name(cached, family_id=family_key):
        return cached
    return _resolve_suffix_name_ru_legacy(family_key, affix_tier)


def representative_affix_tier(tier_rows: list) -> int:
    """Smallest affix_tier in family — stable codex label (see library list)."""
    tiers = [int(getattr(t, "affix_tier", 0) or 0) for t in tier_rows]
    tiers = [t for t in tiers if t > 0]
    return min(tiers) if tiers else 1
