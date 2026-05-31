"""Item generation and management service (templates + affixes)."""
import random
import re
from types import SimpleNamespace
from typing import Any, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from waifu_bot.db import models as m
from waifu_bot.game.passive_affix_ilvl import passive_node_level_add_allowed
from waifu_bot.services.enchanting import apply_enchant_steps_to_inventory_item


RARITY_WEIGHTS = [
    (1, 60),
    (2, 25),
    (3, 10),
    (4, 4),
    (5, 1),
]

AFFIX_COUNT = {
    1: (0, 1),
    2: (1, 2),
    3: (2, 3),
    4: (3, 4),
    5: (0, 0),
}


def _pick_weighted(options: Sequence[tuple[int, int]]) -> int:
    total = sum(w for _, w in options)
    r = random.randint(1, total)
    acc = 0
    for val, w in options:
        acc += w
        if r <= acc:
            return val
    return options[-1][0]


def _tier_from_level(level: int) -> int:
    return max(1, min(10, (level - 1) // 5 + 1))


def _max_base_grade_for_plus(plus_level: int) -> int:
    """Продвинутый: +6+, великолепный: +11+ (аналог Nightmare / Hell)."""
    pl = max(0, int(plus_level or 0))
    if pl <= 5:
        return 0
    if pl <= 10:
        return 1
    return 2


def _roll_base_grade(max_grade: int) -> int:
    mg = max(0, min(2, int(max_grade)))
    if mg <= 0:
        return 0
    if mg == 1:
        return _pick_weighted([(0, 70), (1, 30)])
    return _pick_weighted([(0, 55), (1, 30), (2, 15)])


def _tier_from_item_level_and_grade(item_level: int, base_grade: int) -> int:
    eff = max(1, int(item_level) - int(base_grade) * 5)
    return _tier_from_level(eff)


def _tier_cap_for_act(act: int) -> int:
    return max(1, min(10, act * 2))


_STAT_CODE_TO_NAME: dict[str, str] = {
    "STR": "strength",
    "DEX": "agility",
    "INT": "intelligence",
    "VIT": "endurance",
    "CHA": "charm",
    "LUK": "luck",
}


class ItemService:
    """Service for item generation and management (templates + affixes)."""

    _PRIMARY_STATS: set[str] = {
        "strength",
        "agility",
        "intelligence",
        "endurance",
        "charm",
        "luck",
    }

    _TIER_DELTA_BASE: dict[int, int] = {
        1: 0,
        2: 1,
        3: 2,
        4: 3,
        5: 4,
        6: 5,
        7: 6,
        8: 7,
        9: 8,
        10: 9,
    }

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
            (9, 10): "Трансцендентный",
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
        "s_media_link": {2: "линкера", 4: "URL-мастера", 6: "гиперссылки", 8: "веба", 10: "интернета"},
        "s_dmg_melee": {2: "ближнего боя", 4: "рукопашной резни", 6: "тесаков", 8: "титанов", 10: "бездны ударов"},
        "s_dmg_ranged": {2: "дальнего боя", 4: "меткости", 6: "дождя стрел", 8: "ветра", 10: "небесного лука"},
        "s_dmg_magic": {2: "чар", 4: "заклинаний", 6: "арканы", 8: "бездны маны", 10: "апокалипсиса магии"},
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
        (9, 10): "Трансцендентный",
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
            (7, 8): "URL-ный",
            (9, 10): "Интернетный",
        },
    }

    def _roll_weapon_damage_for_level(self, base_min: int, base_max: int, level: int) -> tuple[int, int]:
        """
        Make stats reflect ilvl within tier.
        Example: for tier1 bow base 7..12 at ilvl=1 -> ~5-7 / 10-12, at ilvl=5 -> 7-7 / 12-12.
        """
        lo = int(base_min)
        hi = int(base_max)
        if hi < lo:
            lo, hi = hi, lo
        if lo <= 0 and hi <= 0:
            return (0, 0)

        lvl = max(1, int(level))
        tier = _tier_from_level(lvl)
        tier_base = (tier - 1) * 5 + 1
        pos = max(0, min(4, lvl - tier_base))
        q = pos / 4.0  # 0..1 inside tier

        # Lower bounds scale up with q; upper bounds stay at base values.
        min_low = max(0, int(round(lo * (0.70 + 0.30 * q))))
        min_high = max(min_low, lo)
        max_low = max(min_high, int(round(hi * (0.83 + 0.17 * q))))
        max_high = max(max_low, hi)

        rolled_min = random.randint(min_low, min_high) if min_high >= min_low else min_low
        rolled_max = random.randint(max_low, max_high) if max_high >= max_low else max_high
        if rolled_max < rolled_min:
            rolled_max = rolled_min
        return int(rolled_min), int(rolled_max)

    def _item_type_from_slot_type(self, slot_type: str | None) -> int:
        st = (slot_type or "").lower()
        if st == "weapon_1h":
            return int(m.ItemType.WEAPON_1)
        if st == "weapon_2h" or st == "offhand":
            return int(m.ItemType.WEAPON_2)
        if st == "costume":
            return int(m.ItemType.COSTUME)
        if st == "ring":
            return int(m.ItemType.RING_1)
        if st == "amulet":
            return int(m.ItemType.AMULET)
        return int(m.ItemType.OTHER)

    async def _diablo_has_content(self, session: AsyncSession) -> bool:
        """
        Check whether Diablo-style base items are available.

        We only require ItemBase rows to exist. Affix families / tiers are optional:
        - if present, they add prefixes/suffixes;
        - if absent, we still use ItemBase as the authoritative source of tier/power
          and simply skip rolling affixes.
        """
        base = await session.scalar(select(m.ItemBase.id).limit(1))
        return bool(base)

    async def _item_base_templates_has_content(self, session: AsyncSession) -> bool:
        """Check whether imported item_base_templates rows are available."""
        try:
            cnt = await session.scalar(text("SELECT COUNT(*) FROM item_base_templates"))
            return bool(int(cnt or 0) > 0)
        except Exception:
            return False

    def _slot_type_from_template_row(self, item_type: str | None, subtype: str | None) -> str:
        it = (item_type or "").lower()
        st = (subtype or "").lower()
        if it == "weapon":
            if st == "one_hand":
                return "weapon_1h"
            if st in {"two_hand", "bow", "staff"}:
                return "weapon_2h"
            if st in {"offhand", "orb"}:
                return "offhand"
            return "weapon_1h"
        if it == "armor":
            return "costume"
        if it == "ring":
            return "ring"
        if it == "amulet":
            return "amulet"
        return "other"

    async def _pick_item_base_template_for_tier_grade(
        self, session: AsyncSession, tier: int, base_grade: int, *, item_rarity: int = 5
    ) -> Optional[dict[str, Any]]:
        """
        Pick weighted random row from item_base_templates for tier + base_grade.
        Fallback: same tier with grade 0, then neighbor tiers, then any tier.
        """
        t = max(1, min(10, int(tier)))
        bg = max(0, min(2, int(base_grade)))
        legend_excl = ""
        if int(item_rarity) < 5:
            legend_excl = (
                " AND COALESCE(secondary_bonus_type, '') NOT ILIKE 'passive_branch_level_add:%' "
                " AND COALESCE(secondary_bonus_type, '') <> 'passive_all_nodes_level_add' "
            )

        async def _one(where_sql: str, params: dict[str, Any]) -> Optional[dict[str, Any]]:
            row = (
                await session.execute(
                    text(
                        f"""
                        SELECT *
                        FROM item_base_templates
                        WHERE COALESCE(base_grade, 0) = :bg
                          AND ({where_sql})
                          {legend_excl}
                        ORDER BY random() * GREATEST(weight, 1) DESC
                        LIMIT 1
                        """
                    ),
                    params,
                )
            ).mappings().first()
            return dict(row) if row else None

        for try_bg in [bg, 0]:
            if try_bg > bg:
                continue
            r = await _one("tier = :tier", {"tier": t, "bg": try_bg})
            if r:
                return r
            r = await _one(
                "tier BETWEEN :tier_min AND :tier_max",
                {
                    "tier": t,
                    "bg": try_bg,
                    "tier_min": max(1, t - 1),
                    "tier_max": min(10, t + 1),
                },
            )
            if r:
                return r
            row = (
                await session.execute(
                    text(
                        f"""
                        SELECT *
                        FROM item_base_templates
                        WHERE COALESCE(base_grade, 0) = :bg
                          {legend_excl}
                        ORDER BY ABS(tier - :tier), random() * GREATEST(weight, 1) DESC
                        LIMIT 1
                        """
                    ),
                    {"bg": try_bg, "tier": t},
                )
            ).mappings().first()
            if row:
                return dict(row)
        return None

    async def _pick_starter_base_template_row(
        self,
        session: AsyncSession,
        *,
        tier: int = 1,
        slot_type: str,
        subtype: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Один случайный шаблон tier/base_grade=0 под слот стартового набора."""
        t = max(1, min(10, int(tier)))
        conds = ["tier = :tier", "COALESCE(base_grade, 0) = 0"]
        params: dict[str, Any] = {"tier": t}
        st = (slot_type or "").strip().lower()
        if st == "weapon_1h":
            conds.append("LOWER(COALESCE(item_type,'')) = 'weapon'")
            conds.append("LOWER(COALESCE(subtype,'')) = 'one_hand'")
        elif st == "weapon_2h":
            conds.append("LOWER(COALESCE(item_type,'')) = 'weapon'")
            if subtype:
                conds.append("LOWER(COALESCE(subtype,'')) = :sub")
                params["sub"] = str(subtype).lower()
            else:
                conds.append(
                    "LOWER(COALESCE(subtype,'')) IN ('two_hand','bow','staff')"
                )
        elif st == "offhand":
            conds.append("LOWER(COALESCE(item_type,'')) = 'weapon'")
            conds.append("LOWER(COALESCE(subtype,'')) IN ('offhand','orb')")
        elif st == "costume":
            conds.append("LOWER(COALESCE(item_type,'')) = 'armor'")
        elif st == "ring":
            conds.append("LOWER(COALESCE(item_type,'')) = 'ring'")
        elif st == "amulet":
            conds.append("LOWER(COALESCE(item_type,'')) = 'amulet'")
        else:
            return None
        where_sql = " AND ".join(conds)
        row = (
            await session.execute(
                text(
                    f"""
                    SELECT * FROM item_base_templates
                    WHERE {where_sql}
                    ORDER BY random() * GREATEST(weight, 1) DESC
                    LIMIT 1
                    """
                ),
                params,
            )
        ).mappings().first()
        return dict(row) if row else None

    async def create_inventory_item_from_starter_base(
        self,
        session: AsyncSession,
        player_id: Optional[int],
        base: dict[str, Any],
        *,
        act: int = 1,
        rarity: int = 1,
        target_level: int = 1,
        plus_level: int = 0,
    ) -> m.InventoryItem:
        """Создать предмет из уже выбранной строки item_base_templates (стартовый набор)."""
        target_total_level = max(1, int(target_level))
        max_g = _max_base_grade_for_plus(plus_level)
        base_grade = _roll_base_grade(max_g)
        tier = _tier_from_item_level_and_grade(target_total_level, base_grade)
        base_tier = int(base.get("tier") or tier)
        base_level = int(base.get("level_min") or max(1, (base_tier - 1) * 5 + 1))
        target_total_level = max(base_level, int(target_total_level))
        slot_type = self._slot_type_from_template_row(base.get("item_type"), base.get("subtype"))

        raw_dmg_min = int(base.get("dmg_min") or 0)
        raw_dmg_max = int(base.get("dmg_max") or 0)
        dmg_min: int | None = raw_dmg_min if raw_dmg_min > 0 else None
        dmg_max: int | None = raw_dmg_max if raw_dmg_max > 0 else None
        if dmg_min is not None and dmg_max is not None:
            try:
                dmg_min, dmg_max = self._roll_weapon_damage_for_level(dmg_min, dmg_max, target_total_level)
            except Exception:
                pass

        raw_attack_speed = int(base.get("attack_speed") or 0)
        attack_speed = raw_attack_speed if raw_attack_speed > 0 else None
        base_stat_code = str(base.get("stat1_type") or "").upper()
        base_stat = _STAT_CODE_TO_NAME.get(base_stat_code)
        base_stat_value = int(base.get("stat1_value") or 0) or None
        req_level = int(base.get("level_min") or max(1, target_total_level - 2))
        req_stat_val = max(0, int(base.get("stat1_value") or 0))
        req = {"level": req_level}
        if base_stat == "strength":
            req["strength"] = req_stat_val
        elif base_stat == "agility":
            req["agility"] = req_stat_val
        elif base_stat == "intelligence":
            req["intelligence"] = req_stat_val
        elif base_stat == "endurance":
            req["endurance"] = req_stat_val

        rr = base.get("required_race")
        if rr is not None and str(rr).strip() != "":
            try:
                req["waifu_race"] = int(rr)
            except (TypeError, ValueError):
                pass
        rc = base.get("required_class")
        if rc is not None and str(rc).strip() != "":
            try:
                req["waifu_class"] = int(rc)
            except (TypeError, ValueError):
                pass

        weapon_type = str(base.get("subtype") or "") or None
        attack_type = str(base.get("attack_type") or "") or None
        name = str(base.get("name") or "Предмет")

        base_value = max(1, int(20 * int(target_total_level) * int(rarity)))
        item = m.Item(
            name=name,
            description=None,
            rarity=int(rarity),
            tier=int(base_tier),
            level=int(target_total_level),
            item_type=self._item_type_from_slot_type(slot_type),
            damage=int(dmg_max) if dmg_max is not None else (int(dmg_min) if dmg_min is not None else None),
            attack_speed=int(attack_speed) if attack_speed is not None else None,
            weapon_type=weapon_type,
            attack_type=attack_type,
            required_level=req.get("level"),
            required_strength=req.get("strength"),
            required_agility=req.get("agility"),
            required_intelligence=req.get("intelligence"),
            affixes=None,
            base_value=base_value,
            is_legendary=False,
        )
        session.add(item)
        await session.flush()

        inv = m.InventoryItem(
            player_id=player_id,
            item_id=item.id,
            rarity=int(rarity),
            tier=int(base_tier),
            level=int(target_total_level),
            base_level=int(base_level),
            total_level=int(target_total_level),
            plus_level_source=max(0, int(plus_level or 0)),
            base_id=None,
            is_legendary=False,
            damage_min=int(dmg_min) if dmg_min is not None else None,
            damage_max=int(dmg_max) if dmg_max is not None else None,
            attack_speed=int(attack_speed) if attack_speed is not None else None,
            attack_type=attack_type,
            weapon_type=weapon_type,
            base_stat=base_stat,
            base_stat_value=int(base_stat_value) if base_stat_value is not None else None,
            requirements=req,
            slot_type=slot_type,
            affixes=[],
        )
        session.add(inv)
        await session.flush()

        min_a, max_a = AFFIX_COUNT.get(int(rarity), (0, 0))
        count = random.randint(min_a, max_a)
        pseudo_base = SimpleNamespace(
            slot_type=slot_type,
            attack_type=attack_type,
        )
        tier_cap = _tier_cap_for_act(act)
        pairs = await self._get_diablo_candidates(
            session, pseudo_base, tier_cap, target_total_level, item_rarity=int(rarity)
        )

        prefixes: list[tuple[m.AffixFamily, m.AffixFamilyTier]] = []
        suffixes: list[tuple[m.AffixFamily, m.AffixFamilyTier]] = []
        for fam, tr in pairs:
            k = (getattr(fam, "kind", "") or "").lower()
            if k == "prefix":
                prefixes.append((fam, tr))
            elif k == "suffix":
                suffixes.append((fam, tr))

        chosen: list[tuple[m.AffixFamily, m.AffixFamilyTier]] = []
        used_family_ids: set[int] = set()
        used_excl: set[str] = set()

        def _try_add(pool: list[tuple[m.AffixFamily, m.AffixFamilyTier]]) -> bool:
            if not pool:
                return False
            fam, tr = random.choice(pool)
            if fam.id in used_family_ids:
                return False
            eg = str(getattr(fam, "exclusive_group", "") or "")
            if eg and eg in used_excl:
                return False
            used_family_ids.add(fam.id)
            if eg:
                used_excl.add(eg)
            chosen.append((fam, tr))
            return True

        if count >= 1 and prefixes:
            _try_add(prefixes)
        attempts = 0
        while len(chosen) < count and attempts < 50:
            attempts += 1
            pool = suffixes if (suffixes and random.random() < 0.35) else prefixes
            if not pool:
                pool = prefixes or suffixes
            if not pool:
                break
            _try_add(pool)

        for fam, tr in chosen:
            vmin = int(tr.value_min or 0)
            vmax = int(tr.value_max or 0)
            if vmax < vmin:
                vmin, vmax = vmax, vmin
            value = random.randint(vmin, vmax) if vmax >= vmin else vmin

            effect_key = str(getattr(fam, "effect_key", "") or "")
            affix_tier = int(getattr(tr, "affix_tier", 1) or 1)
            if effect_key in self._PRIMARY_STATS:
                level_delta = self._compute_level_delta_primary_stat(affix_tier, value, vmin)
            else:
                level_delta = self._compute_level_delta_scaled(
                    value=value,
                    value_min=vmin,
                    value_max=vmax,
                    level_delta_min=int(tr.level_delta_min or 0),
                    level_delta_max=int(tr.level_delta_max or 0),
                )
            ek_low = effect_key.lower()
            if ek_low.startswith("passive_node_level_add:"):
                level_delta = int(level_delta) * int(self._PASSIVE_NODE_AFFIX_LEVEL_DELTA_MULT)

            fam_kind = (getattr(fam, "kind", "") or "").lower()
            inv_kind = "affix" if fam_kind == "prefix" else "suffix"
            if inv_kind == "affix":
                name_ru = self._resolve_prefix_name_ru(effect_key, affix_tier)
            else:
                name_ru = self._resolve_suffix_name_ru(str(getattr(fam, "family_id", "") or ""), affix_tier)

            inv.affixes.append(
                m.InventoryAffix(
                    inventory_item_id=inv.id,
                    name=name_ru,
                    stat=effect_key,
                    value=str(int(value)),
                    is_percent=bool(self._is_percent_effect_key(effect_key)),
                    kind=inv_kind,
                    tier=int(affix_tier),
                    family_id=fam.id,
                    affix_tier=int(affix_tier),
                    exclusive_group=getattr(fam, "exclusive_group", None),
                    level_delta=int(level_delta),
                )
            )

            if inv.damage_min is not None and effect_key == "damage_flat":
                inv.damage_min += int(value)
            if inv.damage_max is not None and effect_key == "damage_flat":
                inv.damage_max += int(value)
            if inv.damage_min is not None and effect_key == "damage_percent":
                inv.damage_min = int(inv.damage_min * (1 + int(value) / 100))
            if inv.damage_max is not None and effect_key == "damage_percent":
                inv.damage_max = int(inv.damage_max * (1 + int(value) / 100))
            inv.total_level = int(inv.total_level) + int(level_delta)

        tpl_ilvl = self._template_secondary_total_level_bonus(base)
        if tpl_ilvl:
            inv.total_level = int(inv.total_level) + int(tpl_ilvl)

        inv.level = int(inv.total_level)
        item.level = int(inv.total_level)
        item.base_value = max(1, int(20 * int(inv.total_level) * int(rarity)))

        await session.flush()
        inv._display_name = item.name  # type: ignore[attr-defined]
        await apply_enchant_steps_to_inventory_item(session, inv)
        await self._register_inventory_codex(session, player_id, inv)
        return inv

    async def _register_inventory_codex(
        self,
        session: AsyncSession,
        player_id: Optional[int],
        inv: m.InventoryItem,
    ) -> None:
        if player_id is None:
            return
        from waifu_bot.services.item_codex import register_inventory_codex

        await register_inventory_codex(session, int(player_id), inv)

    async def _generate_inventory_item_from_base_templates(
        self,
        session: AsyncSession,
        player_id: Optional[int],
        act: int,
        rarity: int,
        level: int | None,
        plus_level: int = 0,
    ) -> m.InventoryItem:
        target_total_level = int(level or max(1, _tier_cap_for_act(act) * 5 - 4 + random.randint(0, 4)))
        max_g = _max_base_grade_for_plus(plus_level)
        base_grade = _roll_base_grade(max_g)
        tier = _tier_from_item_level_and_grade(target_total_level, base_grade)
        base = await self._pick_item_base_template_for_tier_grade(
            session, tier, base_grade, item_rarity=int(rarity)
        )
        if not base:
            raise RuntimeError("No item_base_templates available")

        base_tier = int(base.get("tier") or tier)
        base_level = int(base.get("level_min") or max(1, (base_tier - 1) * 5 + 1))
        target_total_level = max(base_level, int(target_total_level))
        slot_type = self._slot_type_from_template_row(base.get("item_type"), base.get("subtype"))

        raw_dmg_min = int(base.get("dmg_min") or 0)
        raw_dmg_max = int(base.get("dmg_max") or 0)
        dmg_min: int | None = raw_dmg_min if raw_dmg_min > 0 else None
        dmg_max: int | None = raw_dmg_max if raw_dmg_max > 0 else None
        if dmg_min is not None and dmg_max is not None:
            try:
                dmg_min, dmg_max = self._roll_weapon_damage_for_level(dmg_min, dmg_max, target_total_level)
            except Exception:
                pass

        raw_attack_speed = int(base.get("attack_speed") or 0)
        attack_speed = raw_attack_speed if raw_attack_speed > 0 else None
        base_stat_code = str(base.get("stat1_type") or "").upper()
        base_stat = _STAT_CODE_TO_NAME.get(base_stat_code)
        base_stat_value = int(base.get("stat1_value") or 0) or None
        req_level = int(base.get("level_min") or max(1, target_total_level - 2))
        req_stat_val = max(0, int(base.get("stat1_value") or 0))
        req = {"level": req_level}
        if base_stat == "strength":
            req["strength"] = req_stat_val
        elif base_stat == "agility":
            req["agility"] = req_stat_val
        elif base_stat == "intelligence":
            req["intelligence"] = req_stat_val
        elif base_stat == "endurance":
            req["endurance"] = req_stat_val

        rr = base.get("required_race")
        if rr is not None and str(rr).strip() != "":
            try:
                req["waifu_race"] = int(rr)
            except (TypeError, ValueError):
                pass
        rc = base.get("required_class")
        if rc is not None and str(rc).strip() != "":
            try:
                req["waifu_class"] = int(rc)
            except (TypeError, ValueError):
                pass

        weapon_type = str(base.get("subtype") or "") or None
        attack_type = str(base.get("attack_type") or "") or None
        name = str(base.get("name") or "Предмет")

        base_value = max(1, int(20 * int(target_total_level) * int(rarity)))
        item = m.Item(
            name=name,
            description=None,
            rarity=int(rarity),
            tier=int(base_tier),
            level=int(target_total_level),
            item_type=self._item_type_from_slot_type(slot_type),
            damage=int(dmg_max) if dmg_max is not None else (int(dmg_min) if dmg_min is not None else None),
            attack_speed=int(attack_speed) if attack_speed is not None else None,
            weapon_type=weapon_type,
            attack_type=attack_type,
            required_level=req.get("level"),
            required_strength=req.get("strength"),
            required_agility=req.get("agility"),
            required_intelligence=req.get("intelligence"),
            affixes=None,
            base_value=base_value,
            is_legendary=False,
        )
        session.add(item)
        await session.flush()

        inv = m.InventoryItem(
            player_id=player_id,
            item_id=item.id,
            rarity=int(rarity),
            tier=int(base_tier),
            level=int(target_total_level),
            base_level=int(base_level),
            total_level=int(target_total_level),
            plus_level_source=max(0, int(plus_level or 0)),
            base_id=None,
            is_legendary=False,
            damage_min=int(dmg_min) if dmg_min is not None else None,
            damage_max=int(dmg_max) if dmg_max is not None else None,
            attack_speed=int(attack_speed) if attack_speed is not None else None,
            attack_type=attack_type,
            weapon_type=weapon_type,
            base_stat=base_stat,
            base_stat_value=int(base_stat_value) if base_stat_value is not None else None,
            requirements=req,
            slot_type=slot_type,
            affixes=[],
        )
        session.add(inv)
        await session.flush()

        min_a, max_a = AFFIX_COUNT.get(int(rarity), (0, 0))
        count = random.randint(min_a, max_a)
        pseudo_base = SimpleNamespace(
            slot_type=slot_type,
            attack_type=attack_type,
        )
        tier_cap = _tier_cap_for_act(act)
        pairs = await self._get_diablo_candidates(
            session, pseudo_base, tier_cap, target_total_level, item_rarity=int(rarity)
        )

        prefixes: list[tuple[m.AffixFamily, m.AffixFamilyTier]] = []
        suffixes: list[tuple[m.AffixFamily, m.AffixFamilyTier]] = []
        for fam, tr in pairs:
            k = (getattr(fam, "kind", "") or "").lower()
            if k == "prefix":
                prefixes.append((fam, tr))
            elif k == "suffix":
                suffixes.append((fam, tr))

        chosen: list[tuple[m.AffixFamily, m.AffixFamilyTier]] = []
        used_family_ids: set[int] = set()
        used_excl: set[str] = set()

        def _try_add(pool: list[tuple[m.AffixFamily, m.AffixFamilyTier]]) -> bool:
            if not pool:
                return False
            fam, tr = random.choice(pool)
            if fam.id in used_family_ids:
                return False
            eg = str(getattr(fam, "exclusive_group", "") or "")
            if eg and eg in used_excl:
                return False
            used_family_ids.add(fam.id)
            if eg:
                used_excl.add(eg)
            chosen.append((fam, tr))
            return True

        if count >= 1 and prefixes:
            _try_add(prefixes)
        attempts = 0
        while len(chosen) < count and attempts < 50:
            attempts += 1
            pool = suffixes if (suffixes and random.random() < 0.35) else prefixes
            if not pool:
                pool = prefixes or suffixes
            if not pool:
                break
            _try_add(pool)

        for fam, tr in chosen:
            vmin = int(tr.value_min or 0)
            vmax = int(tr.value_max or 0)
            if vmax < vmin:
                vmin, vmax = vmax, vmin
            value = random.randint(vmin, vmax) if vmax >= vmin else vmin

            effect_key = str(getattr(fam, "effect_key", "") or "")
            affix_tier = int(getattr(tr, "affix_tier", 1) or 1)
            if effect_key in self._PRIMARY_STATS:
                level_delta = self._compute_level_delta_primary_stat(affix_tier, value, vmin)
            else:
                level_delta = self._compute_level_delta_scaled(
                    value=value,
                    value_min=vmin,
                    value_max=vmax,
                    level_delta_min=int(tr.level_delta_min or 0),
                    level_delta_max=int(tr.level_delta_max or 0),
                )
            ek_low = effect_key.lower()
            if ek_low.startswith("passive_node_level_add:"):
                level_delta = int(level_delta) * int(self._PASSIVE_NODE_AFFIX_LEVEL_DELTA_MULT)

            fam_kind = (getattr(fam, "kind", "") or "").lower()
            inv_kind = "affix" if fam_kind == "prefix" else "suffix"
            if inv_kind == "affix":
                name_ru = self._resolve_prefix_name_ru(effect_key, affix_tier)
            else:
                name_ru = self._resolve_suffix_name_ru(str(getattr(fam, "family_id", "") or ""), affix_tier)

            inv.affixes.append(
                m.InventoryAffix(
                    inventory_item_id=inv.id,
                    name=name_ru,
                    stat=effect_key,
                    value=str(int(value)),
                    is_percent=bool(self._is_percent_effect_key(effect_key)),
                    kind=inv_kind,
                    tier=int(affix_tier),
                    family_id=fam.id,
                    affix_tier=int(affix_tier),
                    exclusive_group=getattr(fam, "exclusive_group", None),
                    level_delta=int(level_delta),
                )
            )

            if inv.damage_min is not None and effect_key == "damage_flat":
                inv.damage_min += int(value)
            if inv.damage_max is not None and effect_key == "damage_flat":
                inv.damage_max += int(value)
            if inv.damage_min is not None and effect_key == "damage_percent":
                inv.damage_min = int(inv.damage_min * (1 + int(value) / 100))
            if inv.damage_max is not None and effect_key == "damage_percent":
                inv.damage_max = int(inv.damage_max * (1 + int(value) / 100))
            inv.total_level = int(inv.total_level) + int(level_delta)

        tpl_ilvl = self._template_secondary_total_level_bonus(base)
        if tpl_ilvl:
            inv.total_level = int(inv.total_level) + int(tpl_ilvl)

        inv.level = int(inv.total_level)
        item.level = int(inv.total_level)
        item.base_value = max(1, int(20 * int(inv.total_level) * int(rarity)))

        await session.flush()
        inv._display_name = item.name  # type: ignore[attr-defined]
        await apply_enchant_steps_to_inventory_item(session, inv)
        return inv

    def _is_percent_effect_key(self, effect_key: str) -> bool:
        k = (effect_key or "").lower()
        if k.startswith("passive_node_level_add:") or k.startswith("passive_branch_level_add:"):
            return False
        if k == "passive_all_nodes_level_add":
            return False
        return (
            k.endswith("_percent")
            or k.endswith("_pct")
            or k.startswith("media_damage_")
            or ":percent" in k
        )

    def _resolve_prefix_name_ru(self, stat: str, affix_tier: int) -> str:
        st = str(stat or "")
        low = st.lower().replace("audioo", "audio").replace("magii", "magic")
        if low.startswith("passive_node_level_add:") or low.startswith(
            "passive_branch_level_add:"
        ):
            tr = int(affix_tier)
            for (a, b), name in self._PASSIVE_LEVEL_ADD_PREFIX.items():
                if a <= tr <= b:
                    return name
            return "Наставнический"
        if low == "passive_all_nodes_level_add":
            tr = int(affix_tier)
            for (a, b), name in self._PASSIVE_LEVEL_ADD_PREFIX.items():
                if a <= tr <= b:
                    return name
            return "Наставнический"
        sec_ranges = self._SECONDARY_PREFIX_NAMES.get(low) or {}
        for (a, b), name in sec_ranges.items():
            if a <= int(affix_tier) <= b:
                return name
        ranges = self._PREFIX_NAME_BY_STAT.get(low) or {}
        for (a, b), name in ranges.items():
            if a <= affix_tier <= b:
                return name
        # fallback
        return (stat or "").capitalize() or "Префикс"

    def _resolve_suffix_name_ru(self, family_key: str, affix_tier: int) -> str:
        fk = str(family_key or "")
        if fk.startswith("s_passive_lvl_") or fk.startswith("s_passive_branch_"):
            return self._PASSIVE_LEVEL_ADD_SUFFIX.get(int(affix_tier), "наставления")
        if fk == "s_passive_all":
            return self._PASSIVE_LEVEL_ADD_SUFFIX.get(int(affix_tier), "наставления")
        per_tier = self._SUFFIX_NAME_BY_FAMILY_ID.get(family_key) or {}
        if per_tier:
            return per_tier.get(int(affix_tier), family_key)
        mm = re.match(r"^s_monster_(\w+)_(flat|pct)$", fk, re.IGNORECASE)
        if mm:
            fam = mm.group(1).lower()
            return self._MONSTER_FAMILY_GENITIVE_RU.get(fam, fam)
        return family_key

    def _compute_level_delta_primary_stat(self, affix_tier: int, value: int, value_min: int) -> int:
        base = int(self._TIER_DELTA_BASE.get(int(affix_tier), 0))
        return base + max(0, int(value) - int(value_min))

    def _compute_level_delta_scaled(
        self,
        value: int,
        value_min: int,
        value_max: int,
        level_delta_min: int,
        level_delta_max: int,
    ) -> int:
        # scale by percentile inside [value_min..value_max]
        span_v = max(1, int(value_max) - int(value_min))
        span_d = int(level_delta_max) - int(level_delta_min)
        pos = max(0, min(span_v, int(value) - int(value_min)))
        return int(level_delta_min) + (pos * span_d) // span_v

    def _weapon_damage_effect_matches_item(
        self,
        effect_key: str,
        slot_type: str | None,
        attack_type: str | None,
        weapon_type: str | None,
    ) -> bool:
        """Плоский урон по типу атаки — только соответствующий оружию (лук ≠ ближний бой)."""
        ek = (effect_key or "").strip().lower()
        if ek not in ("melee_damage_flat", "ranged_damage_flat", "magic_damage_flat"):
            return True
        st = (slot_type or "").lower()
        if "weapon" not in st:
            return True
        at = (attack_type or "").strip().lower() if attack_type else ""
        if not at:
            wt = (weapon_type or "").lower()
            if "bow" in wt:
                at = "ranged"
            elif any(x in wt for x in ("staff", "wand", "orb")):
                at = "magic"
            elif wt:
                at = "melee"
        if at == "melee":
            return ek == "melee_damage_flat"
        if at == "ranged":
            return ek == "ranged_damage_flat"
        if at == "magic":
            return ek == "magic_damage_flat"
        return True

    def _family_allows_base(self, family: m.AffixFamily, base: m.ItemBase) -> bool:
        """
        Minimal constraints handling for allowed_slot_types / allowed_attack_types.
        We use the JSON shape seeded by our docs: {"include": [..]} / {"exclude": [..]}.
        """
        st = (base.slot_type or "").lower()
        at = (base.attack_type or "").lower() if base.attack_type else ""

        allowed_st = getattr(family, "allowed_slot_types", None) or None
        if isinstance(allowed_st, dict):
            inc = [str(x).lower() for x in (allowed_st.get("include") or [])]
            exc = [str(x).lower() for x in (allowed_st.get("exclude") or [])]
            if inc and st not in inc:
                return False
            if exc and st in exc:
                return False

        allowed_at = getattr(family, "allowed_attack_types", None) or None
        if isinstance(allowed_at, dict):
            inc = [str(x).lower() for x in (allowed_at.get("include") or [])]
            exc = [str(x).lower() for x in (allowed_at.get("exclude") or [])]
            if inc and at not in inc:
                return False
            if exc and at in exc:
                return False

        return True

    @staticmethod
    def _effect_key_requires_legendary(effect_key: str) -> bool:
        k = str(effect_key or "").strip().lower()
        return k.startswith("passive_branch_level_add:") or k == "passive_all_nodes_level_add"

    def _template_secondary_total_level_bonus(self, base: dict[str, Any]) -> int:
        """Доп. ilvl от вторички шаблона (влияет на total_level, цену, отображение уровня)."""
        st = str(base.get("secondary_bonus_type") or "").strip().lower()
        try:
            sv = float(base.get("secondary_bonus_value") or 0.0)
        except (TypeError, ValueError):
            return 0
        if not st or sv <= 0:
            return 0
        if st.startswith("passive_node_level_add:"):
            return max(0, int(round(sv))) * 10
        if st.startswith("passive_branch_level_add:"):
            return max(0, int(round(sv))) * 40
        if st == "passive_all_nodes_level_add":
            return max(0, int(round(sv))) * 90
        if st in self._TEMPLATE_FRACTION_SECONDARIES:
            return max(0, min(6, int(round(sv * 200))))
        return 0

    async def _pick_diablo_base(
        self, session: AsyncSession, tier_cap: int, target_total_level: int
    ) -> m.ItemBase | None:
        """
        Pick an ItemBase that is compatible with act tier cap and target level.
        Important: base_level should not exceed target_total_level, otherwise we'd create
        inconsistent items (e.g., tier2 affixes but total_level=3).
        """
        tgt = max(1, int(target_total_level))
        res = await session.execute(select(m.ItemBase))
        bases = res.scalars().all()
        if not bases:
            return None

        candidates: list[m.ItemBase] = []
        weights: list[int] = []
        for b in bases:
            tags = getattr(b, "tags", None) or {}
            try:
                bt = int((tags or {}).get("tier"))
            except Exception:
                bt = None
            if bt is not None and bt > int(tier_cap):
                continue

            bl = getattr(b, "base_level_min", None)
            try:
                base_level = int(bl) if bl is not None else 1
            except Exception:
                base_level = 1
            if base_level > tgt:
                continue

            # Weight by closeness (prefer bases near the target to reduce delta pressure)
            dist = abs(tgt - base_level)
            w = max(1, 30 - min(29, dist * 6))
            candidates.append(b)
            weights.append(w)

        if not candidates:
            return None
        return random.choices(candidates, weights=weights, k=1)[0]

    async def _get_diablo_candidates(
        self,
        session: AsyncSession,
        base: m.ItemBase,
        tier_cap: int,
        target_total_level: int,
        *,
        item_rarity: int = 5,
    ) -> list[tuple[m.AffixFamily, m.AffixFamilyTier]]:
        stmt = (
            select(m.AffixFamilyTier, m.AffixFamily)
            .join(m.AffixFamily, m.AffixFamilyTier.family_id == m.AffixFamily.id)
            .where(
                m.AffixFamilyTier.affix_tier <= int(tier_cap),
                m.AffixFamilyTier.min_total_level <= int(target_total_level),
                m.AffixFamilyTier.max_total_level >= int(target_total_level),
            )
        )
        res = await session.execute(stmt)
        pairs: list[tuple[m.AffixFamily, m.AffixFamilyTier]] = []
        rar = int(item_rarity)
        slot_t = getattr(base, "slot_type", None)
        atk_t = getattr(base, "attack_type", None)
        wpn_t = getattr(base, "weapon_type", None)
        for tier_row, fam in res.all():
            ek = str(getattr(fam, "effect_key", "") or "")
            if rar < 5 and self._effect_key_requires_legendary(ek):
                continue
            if not self._weapon_damage_effect_matches_item(ek, slot_t, atk_t, wpn_t):
                continue
            if not self._family_allows_base(fam, base):
                continue
            if not passive_node_level_add_allowed(ek, int(target_total_level)):
                continue
            pairs.append((fam, tier_row))
        return pairs

    async def _generate_inventory_item_diablo(
        self,
        session: AsyncSession,
        player_id: Optional[int],
        act: int,
        rarity: int,
        level: int | None,
    ) -> m.InventoryItem:
        tier_cap = _tier_cap_for_act(act)
        # Choose a target level within act tier (kept compatible with current shop expectations).
        target_total_level = int(level or max(1, tier_cap * 5 - 4 + random.randint(0, 4)))
        base = await self._pick_diablo_base(session, tier_cap, target_total_level)
        if not base:
            raise RuntimeError("No diablo item bases available")

        base_level = int(getattr(base, "base_level_min", None) or 1)
        target_total_level = max(base_level, target_total_level)

        # Tier is a property of the BASE (sword-1 vs sword-2), not derived from ilvl.
        tags = getattr(base, "tags", None) or {}
        try:
            base_tier = int((tags or {}).get("tier"))
        except Exception:
            base_tier = _tier_from_level(int(base_level))

        base_value = max(1, int(20 * int(target_total_level) * int(rarity)))

        implicit = getattr(base, "implicit_effects", None) or {}
        dmg_min = implicit.get("damage_min")
        dmg_max = implicit.get("damage_max")
        atk_speed = implicit.get("attack_speed")
        base_stat = implicit.get("base_stat")
        base_stat_value = implicit.get("base_stat_value")

        # Roll weapon damage by ilvl within tier.
        if dmg_min is not None and dmg_max is not None:
            try:
                rmin, rmax = self._roll_weapon_damage_for_level(int(dmg_min), int(dmg_max), int(target_total_level))
                dmg_min, dmg_max = rmin, rmax
            except Exception:
                pass

        item = m.Item(
            name=base.name_ru,
            description=None,
            rarity=int(rarity),
            tier=int(base_tier),
            level=int(target_total_level),
            item_type=self._item_type_from_slot_type(base.slot_type),
            damage=int(dmg_max) if dmg_max is not None else (int(dmg_min) if dmg_min is not None else None),
            attack_speed=int(atk_speed) if atk_speed is not None else None,
            weapon_type=base.weapon_type,
            attack_type=base.attack_type,
            required_level=(base.requirements or {}).get("level"),
            required_strength=(base.requirements or {}).get("strength"),
            required_agility=(base.requirements or {}).get("agility"),
            required_intelligence=(base.requirements or {}).get("intelligence"),
            affixes=None,
            base_value=base_value,
            is_legendary=False,
        )
        session.add(item)
        await session.flush()

        inv = m.InventoryItem(
            player_id=player_id,
            item_id=item.id,
            rarity=int(rarity),
            tier=int(base_tier),
            level=int(target_total_level),  # kept for compatibility; total_level is authoritative for Diablo
            base_level=int(base_level),
            total_level=int(base_level),
            base_id=base.id,
            is_legendary=False,
            damage_min=int(dmg_min) if dmg_min is not None else None,
            damage_max=int(dmg_max) if dmg_max is not None else None,
            attack_speed=int(atk_speed) if atk_speed is not None else None,
            attack_type=base.attack_type,
            weapon_type=base.weapon_type,
            base_stat=str(base_stat) if base_stat else None,
            base_stat_value=int(base_stat_value) if base_stat_value is not None else None,
            requirements=base.requirements,
            slot_type=base.slot_type,
            affixes=[],
        )
        session.add(inv)
        await session.flush()

        min_a, max_a = AFFIX_COUNT.get(int(rarity), (0, 0))
        count = random.randint(min_a, max_a)
        pairs = await self._get_diablo_candidates(
            session, base, tier_cap, target_total_level, item_rarity=int(rarity)
        )

        # Partition by family kind.
        prefixes: list[tuple[m.AffixFamily, m.AffixFamilyTier]] = []
        suffixes: list[tuple[m.AffixFamily, m.AffixFamilyTier]] = []
        for fam, tr in pairs:
            k = (getattr(fam, "kind", "") or "").lower()
            if k == "prefix":
                prefixes.append((fam, tr))
            elif k == "suffix":
                suffixes.append((fam, tr))

        chosen: list[tuple[m.AffixFamily, m.AffixFamilyTier]] = []
        used_family_ids: set[int] = set()
        used_excl: set[str] = set()

        def _try_add(pool: list[tuple[m.AffixFamily, m.AffixFamilyTier]]) -> bool:
            if not pool:
                return False
            fam, tr = random.choice(pool)
            if fam.id in used_family_ids:
                return False
            eg = str(getattr(fam, "exclusive_group", "") or "")
            if eg and eg in used_excl:
                return False
            used_family_ids.add(fam.id)
            if eg:
                used_excl.add(eg)
            chosen.append((fam, tr))
            return True

        # Ensure at least one prefix when we have slots and prefixes exist.
        if count >= 1 and prefixes:
            _try_add(prefixes)
        # Then fill remaining with mixed pools.
        attempts = 0
        while len(chosen) < count and attempts < 50:
            attempts += 1
            pool = suffixes if (suffixes and random.random() < 0.35) else prefixes
            if not pool:
                pool = prefixes or suffixes
            if not pool:
                break
            _try_add(pool)

        # Roll and apply affixes
        for fam, tr in chosen:
            vmin = int(tr.value_min or 0)
            vmax = int(tr.value_max or 0)
            if vmax < vmin:
                vmin, vmax = vmax, vmin
            value = random.randint(vmin, vmax) if vmax >= vmin else vmin

            effect_key = str(getattr(fam, "effect_key", "") or "")
            affix_tier = int(getattr(tr, "affix_tier", 1) or 1)

            if effect_key in self._PRIMARY_STATS:
                level_delta = self._compute_level_delta_primary_stat(affix_tier, value, vmin)
            else:
                level_delta = self._compute_level_delta_scaled(
                    value=value,
                    value_min=vmin,
                    value_max=vmax,
                    level_delta_min=int(tr.level_delta_min or 0),
                    level_delta_max=int(tr.level_delta_max or 0),
                )
            ek_low = effect_key.lower()
            if ek_low.startswith("passive_node_level_add:"):
                level_delta = int(level_delta) * int(self._PASSIVE_NODE_AFFIX_LEVEL_DELTA_MULT)

            fam_kind = (getattr(fam, "kind", "") or "").lower()
            inv_kind = "affix" if fam_kind == "prefix" else "suffix"
            if inv_kind == "affix":
                name_ru = self._resolve_prefix_name_ru(effect_key, affix_tier)
            else:
                name_ru = self._resolve_suffix_name_ru(str(getattr(fam, "family_id", "") or ""), affix_tier)

            inv.affixes.append(
                m.InventoryAffix(
                    inventory_item_id=inv.id,
                    name=name_ru,
                    stat=effect_key,
                    value=str(int(value)),
                    is_percent=bool(self._is_percent_effect_key(effect_key)),
                    kind=inv_kind,
                    tier=int(affix_tier),
                    family_id=fam.id,
                    affix_tier=int(affix_tier),
                    exclusive_group=getattr(fam, "exclusive_group", None),
                    level_delta=int(level_delta),
                )
            )

            # Apply damage-only effects directly to weapon stats (legacy behavior)
            if inv.damage_min is not None and effect_key == "damage_flat":
                inv.damage_min += int(value)
            if inv.damage_max is not None and effect_key == "damage_flat":
                inv.damage_max += int(value)
            if inv.damage_min is not None and effect_key == "damage_percent":
                inv.damage_min = int(inv.damage_min * (1 + int(value) / 100))
            if inv.damage_max is not None and effect_key == "damage_percent":
                inv.damage_max = int(inv.damage_max * (1 + int(value) / 100))

            inv.total_level = int(inv.total_level) + int(level_delta)

        # Finalize coherence: ilvl follows total_level; tier remains base-tier
        inv.level = int(inv.total_level)
        item.level = int(inv.total_level)
        item.base_value = max(1, int(20 * int(inv.total_level) * int(rarity)))

        await session.flush()
        # Attach display name so callers don't need to lazy-load inv.item in async context
        inv._display_name = item.name  # type: ignore[attr-defined]
        await apply_enchant_steps_to_inventory_item(session, inv)
        return inv

    async def generate_inventory_item(
        self,
        session: AsyncSession,
        player_id: Optional[int],
        act: int,
        rarity: Optional[int] = None,
        level: Optional[int] = None,
        is_shop: bool = False,
        plus_level: int = 0,
    ) -> m.InventoryItem:
        rarity = rarity or _pick_weighted(RARITY_WEIGHTS)
        level = level or max(1, _tier_cap_for_act(act) * 5 - 4 + random.randint(0, 4))
        tier = _tier_from_level(level)
        tier_cap = _tier_cap_for_act(act)
        pl_src = 0 if is_shop else max(0, int(plus_level or 0))

        # Prefer imported item_base_templates first (10-tier content source).
        try:
            if await self._item_base_templates_has_content(session):
                inv = await self._generate_inventory_item_from_base_templates(
                    session,
                    player_id=player_id,
                    act=act,
                    rarity=int(rarity),
                    level=int(level) if level is not None else None,
                    plus_level=pl_src,
                )
                await self._register_inventory_codex(session, player_id, inv)
                return inv
        except Exception:
            # keep current behavior if the table is absent/incompatible
            pass

        # Then prefer Diablo-style generator if content exists; finally fall back to legacy templates/affixes.
        try:
            if await self._diablo_has_content(session):
                inv = await self._generate_inventory_item_diablo(
                    session,
                    player_id=player_id,
                    act=act,
                    rarity=int(rarity),
                    level=int(level) if level is not None else None,
                )
                await self._register_inventory_codex(session, player_id, inv)
                return inv
        except Exception:
            # keep legacy behavior on any Diablo error
            pass

        template = await self._pick_template(session, tier_cap)
        if not template:
            raise RuntimeError("No item templates available for generation")

        # Create an Item row so UI can show proper name/metadata.
        base_value = max(1, int(20 * int(level) * int(rarity)))

        # Roll weapon damage by ilvl within tier (so lvl 3 and lvl 10 differ).
        dmg_min = template.base_damage_min
        dmg_max = template.base_damage_max
        if dmg_min is not None and dmg_max is not None:
            try:
                dmg_min, dmg_max = self._roll_weapon_damage_for_level(int(dmg_min), int(dmg_max), int(level))
            except Exception:
                pass
        item = m.Item(
            name=template.name,
            description=None,
            rarity=int(rarity),
            tier=int(tier),
            level=int(level),
            item_type=self._item_type_from_slot_type(template.slot_type),
            damage=int(dmg_max) if dmg_max is not None else (int(dmg_min) if dmg_min is not None else None),
            attack_speed=template.base_attack_speed,
            weapon_type=template.weapon_type,
            attack_type=template.attack_type,
            required_level=(template.requirements or {}).get("level"),
            required_strength=(template.requirements or {}).get("strength"),
            required_agility=(template.requirements or {}).get("agility"),
            required_intelligence=(template.requirements or {}).get("intelligence"),
            affixes=None,
            base_value=base_value,
            is_legendary=False,
        )
        session.add(item)
        await session.flush()

        inv = m.InventoryItem(
            player_id=player_id,
            item_id=item.id,
            rarity=rarity,
            tier=tier,
            level=level,
            is_legendary=False,
            damage_min=int(dmg_min) if dmg_min is not None else None,
            damage_max=int(dmg_max) if dmg_max is not None else None,
            attack_speed=template.base_attack_speed,
            attack_type=template.attack_type,
            weapon_type=template.weapon_type,
            base_stat=template.base_stat,
            base_stat_value=template.base_stat_value,
            requirements=template.requirements,
            slot_type=template.slot_type,
            affixes=[],
        )
        session.add(inv)
        await session.flush()

        min_a, max_a = AFFIX_COUNT.get(rarity, (0, 0))
        count = random.randint(min_a, max_a)
        candidates = await self._get_affix_candidates(session, template, level, tier_cap)
        rolled = random.sample(candidates, k=min(count, len(candidates))) if candidates else []

        dmg_flat = 0
        dmg_pct = 0
        for aff in rolled:
            val = random.randint(aff.value_min, aff.value_max)
            inv.affixes.append(
                m.InventoryAffix(
                    inventory_item_id=inv.id,
                    name=aff.name,
                    stat=aff.stat,
                    value=str(val),
                    is_percent=aff.is_percent,
                    kind=aff.kind,
                    tier=aff.tier,
                )
            )
            if aff.stat == "damage_flat":
                dmg_flat += val
            if aff.stat == "damage_pct":
                dmg_pct += val

        if inv.damage_min is not None:
            inv.damage_min = int((inv.damage_min + dmg_flat) * (1 + dmg_pct / 100))
        if inv.damage_max is not None:
            inv.damage_max = int((inv.damage_max + dmg_flat) * (1 + dmg_pct / 100))

        await session.flush()
        # Attach display name so callers don't need to lazy-load inv.item in async context
        inv._display_name = item.name  # type: ignore[attr-defined]
        await apply_enchant_steps_to_inventory_item(session, inv)
        await self._register_inventory_codex(session, player_id, inv)
        return inv

    async def generate_gamble_item(self, session: AsyncSession, act: int, player_level: int) -> m.InventoryItem:
        """Generate gamble item (uncommon-epic) into inventory."""
        rarity = _pick_weighted([(2, 60), (3, 30), (4, 10)])
        level = max(1, min(player_level + 5, _tier_cap_for_act(act) * 5 - 4 + random.randint(0, 4)))
        return await self.generate_inventory_item(session, player_id=player_level, act=act, rarity=rarity, level=level)

    async def _pick_template(self, session: AsyncSession, tier_cap: int) -> Optional[m.ItemTemplate]:
        res = await session.execute(
            select(m.ItemTemplate).where(m.ItemTemplate.base_tier <= tier_cap)
        )
        templates = res.scalars().all()
        if not templates:
            return None
        return random.choice(templates)

    async def _get_affix_candidates(
        self, session: AsyncSession, template: m.ItemTemplate, level: int, tier_cap: int
    ) -> list[m.Affix]:
        tags = {"any", template.slot_type}
        if template.attack_type:
            tags.add(template.attack_type)
        if template.weapon_type:
            tags.add(template.weapon_type)
        res = await session.execute(
            select(m.Affix).where(
                m.Affix.tier <= tier_cap,
                m.Affix.min_level <= level,
            )
        )
        affixes = []
        for aff in res.scalars().all():
            applies = aff.applies_to or []
            if isinstance(applies, dict):
                applies = applies.get("tags", [])
            if "any" in applies or tags.intersection(applies):
                affixes.append(aff)
        return affixes

