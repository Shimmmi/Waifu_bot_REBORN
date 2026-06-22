#!/usr/bin/env python3
"""
Populate item_base_templates.base_grade 1 and 2 (продвинутый / великолепный).

Запуск после alembic upgrade (колонка base_grade):
  python scripts/seed_item_base_grades.py

Удаляет существующие строки с base_grade IN (1,2) и вставляет заново из base_grade=0.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import text

from waifu_bot.db.session import get_session, init_engine

# Канонические имена базового оружия (для сопоставления строки независимо от порядка id в БД)
CANON_WEAPON_LINES: tuple[tuple[str, ...], ...] = (
    (
        "Кинжал",
        "Нож охотника",
        "Вакидзаши",
        "Короткий клинок",
        "Гладиус",
        "Ятаган",
        "Фальшион",
        "Кортик",
        "Мистерикл",
        "Теневое жало",
    ),
    (
        "Меч",
        "Арминг-сворд",
        "Длинный меч",
        "Бастард-сворд",
        "Катана",
        "Палаш",
        "Клеймор",
        "Волчья сталь",
        "Рунный меч",
        "Экскалибур",
    ),
    (
        "Ручной топор",
        "Боевой топор",
        "Секира",
        "Бродакс",
        "Боевая секира",
        "Варварский топор",
        "Великий топор",
        "Рунный топор",
        "Призывной топор",
        "Топор бури",
    ),
    (
        "Короткий лук",
        "Длинный лук",
        "Охотничий лук",
        "Составной лук",
        "Военный лук",
        "Рекурсивный лук",
        "Эльфийский лук",
        "Длань леса",
        "Серебряная дуга",
        "Звёздный лук",
    ),
    (
        "Посох",
        "Ореховый посох",
        "Боевой посох",
        "Жезл силы",
        "Посох тайн",
        "Лунный посох",
        "Архимагов посох",
        "Посох звёзд",
        "Скипетр бездны",
        "Посох Творения",
    ),
    (
        "Деревянный щит",
        "Кожаный щит",
        "Круглый щит",
        "Боевой щит",
        "Рыцарский щит",
        "Башенный щит",
        "Эгида",
        "Щит хранителя",
        "Зеркальный щит",
        "Несокрушимый",
    ),
    (
        "Жезл искр",
        "Угольный жезл",
        "Жезл молнии",
        "Жезл пронзания",
        "Жезл власти",
        "Жезл пустоты",
        "Жезл звёзд",
        "Жезл разлома",
        "Жезл конца",
        "Жезл сотворения",
    ),
    (
        "Дубина",
        "Булава стража",
        "Таранная булава",
        "Булава карателя",
        "Утренняя звезда",
        "Булава инквизитора",
        "Шипастый шар",
        "Булава титанов",
        "Булава падших",
        "Булава конца времён",
    ),
    (
        "Короткое копьё",
        "Пика легиона",
        "Копьё охотника",
        "Спинтон",
        "Копьё фаланги",
        "Копьё дракона",
        "Пика грома",
        "Копьё героя",
        "Алебарда стража",
        "Копьё миров",
    ),
    (
        "Лёгкий арбалет",
        "Арбалет охотника",
        "Тяжёлый арбалет",
        "Арбалет стрелка",
        "Арбалет гарнизона",
        "Осадный арбалет",
        "Арбалет чародея",
        "Серебряный болт",
        "Арбалет призрака",
        "Арбалет звёзд",
    ),
    (
        "Скипетр послушника",
        "Скипетр аколита",
        "Скипетр жреца",
        "Скипетр прорицателя",
        "Скипетр иерарха",
        "Скипетр света",
        "Скипетр суда",
        "Скипетр культа",
        "Скипетр апостола",
        "Скипетр верховного",
    ),
    (
        "Молот кузнеца",
        "Боевой молот",
        "Молот карателя",
        "Молот великана",
        "Молот войны",
        "Молот бури",
        "Молот титана",
        "Рунный молот",
        "Молот падших богов",
        "Молот мирового древа",
    ),
    (
        "Стеклянная сфера",
        "Сфера ученика",
        "Осколок маны",
        "Сфера фокусировки",
        "Сфера дуги",
        "Сфера вихря",
        "Сфера наставника",
        "Сфера бездны",
        "Сфера затмения",
        "Сфера Творения",
    ),
)


def _weapon_line_from_canon_name(name: str, tier: int) -> int | None:
    nm = str(name or "").strip()
    t = int(tier)
    for li, names in enumerate(CANON_WEAPON_LINES):
        if 1 <= t <= len(names) and names[t - 1] == nm:
            return li
    return None


# ── Уникальные имена: оружие (12 линеек × 10 тиров)
WEAPON_ADV: list[list[str]] = [
    [
        "Стилет",
        "Клык степи",
        "Танто мастера",
        "Клинок сумерек",
        "Спата карателя",
        "Крис кровопийца",
        "Секач бури",
        "Игла рока",
        "Клинок бездны",
        "Жало прародителя",
    ],
    [
        "Боевой клинок",
        "Фламберг",
        "Цвайхандер",
        "Клейбарг",
        "Вакидзаси дуэлянта",
        "Сабля наёмника",
        "Двуручник грома",
        "Клинок волчьей стаи",
        "Меч рунного пламени",
        "Клинок коронованный",
    ],
    [
        "Тесак ярости",
        "Секач викинга",
        "Бердыш вождя",
        "Топор казни",
        "Секира карателя",
        "Боевой колун",
        "Топор урагана",
        "Рунный раскалыватель",
        "Топор призыва теней",
        "Секира ледяного ветра",
    ],
    [
        "Лук следопыта",
        "Дуга стрелка",
        "Лук лунной тропы",
        "Составной клык",
        "Лук осадного отряда",
        "Рекурсивный призрак",
        "Эльфийская смерть",
        "Длань пернатых",
        "Серебряная кара",
        "Звёздный залп",
    ],
    [
        "Жезл искажения",
        "Посох дикой рощи",
        "Скипетр разлома",
        "Жезл поглощения",
        "Посох запретной дуги",
        "Лунный разряд",
        "Посох звёздного дождя",
        "Скипетр бездонной тьмы",
        "Жезл разорванной ткани",
        "Скипетр Творящего огня",
    ],
    [
        "Баклер мастера",
        "Щит следопыта",
        "Павеза",
        "Башенный бастион",
        "Щит рыцаря кошмара",
        "Башня железа",
        "Эгида заката",
        "Щит хранителя миров",
        "Зеркало рока",
        "Эгида небес",
    ],
    [
        "Искрящий жезл",
        "Жезл пепла",
        "Перунник",
        "Стержень пронзения",
        "Жезл узурпатора",
        "Стержень пустоты",
        "Жезл семи звёзд",
        "Жезл раскола",
        "Жезл последнего часа",
        "Жезл первоистока",
    ],
    [
        "Боевая дубина",
        "Булава стражника",
        "Таранный шар",
        "Булава палача",
        "Звезда рассвета",
        "Булава фанатика",
        "Шипастый ужас",
        "Булава колоссов",
        "Булава проклятых",
        "Булава вечности",
    ],
    [
        "Пика новобранца",
        "Копьё легионера",
        "Пика тумана",
        "Длинный спинтон",
        "Копьё фаллангиста",
        "Пика чешуи",
        "Громовое копьё",
        "Копьё чемпиона",
        "Алебарда карателя",
        "Копьё королей мира",
    ],
    [
        "Арбалет разведчика",
        "Болтник следопыта",
        "Тяжёлый болт",
        "Арбалет наёмника",
        "Болт гарнизона",
        "Осадный механизм",
        "Арбалет чар",
        "Серебряная смерть",
        "Фантомный болт",
        "Звёздный залп болтов",
    ],
    [
        "Посох послушания",
        "Скипетр посвящения",
        "Жезл обряда",
        "Скипетр предвидения",
        "Скипетр ордена",
        "Скипетр сияния",
        "Скипетр приговора",
        "Скипетр тайного культа",
        "Скипетр избранного",
        "Скипетр верховенства",
    ],
    [
        "Молот подмастерья",
        "Тяжёлый кувалда",
        "Молот палача",
        "Крушитель великанов",
        "Молот легиона",
        "Молот урагана",
        "Молот титанов",
        "Рунный крушитель",
        "Молот падших",
        "Молот корней мира",
    ],
    [
        "Осколок звёздного стекла",
        "Сфера пробуждающейся дуги",
        "Кристалл текущей маны",
        "Фокусирующий шар",
        "Сфера дуги молний",
        "Вихревая сфера",
        "Сфера наставника тайн",
        "Шар бездонной тьмы",
        "Сфера двойного затмения",
        "Сфера сотворения миров",
    ],
]

WEAPON_MAG: list[list[str]] = [
    [
        "Обсидиановый клинок",
        "Клык виверны",
        "Клинок двух лун",
        "Игла Левиафана",
        "Ката кошмара",
        "Зуб прародителя",
        "Резак миров",
        "Клинок затишья",
        "Игла Рагнарёка",
        "Ночное солнце",
    ],
    [
        "Клинок чёрного пламени",
        "Меч затмения",
        "Двуручник титана",
        "Клеймор бездны",
        "Катана кровавой луны",
        "Клинок семи королей",
        "Волчий закат",
        "Рунный пожиратель",
        "Клинок вечного суда",
        "Эскалибур теней",
    ],
    [
        "Топор мирового древа",
        "Секира йотунов",
        "Бездонный колун",
        "Топор крушителя небес",
        "Секира карающего грома",
        "Топор из плоти дракона",
        "Великий раскол",
        "Рунный разрушитель миров",
        "Топор призыва бури",
        "Секира ледяной бездны",
    ],
    [
        "Лук феникса",
        "Дуга звёздного дождя",
        "Лук солнечного затмения",
        "Сердце бури",
        "Лук осадной звезды",
        "Рекурсивная вечность",
        "Эльфийская погибель",
        "Длань первобытного леса",
        "Серебряная комета",
        "Звёздный приговор",
    ],
    [
        "Посох белого пламени",
        "Скипетр запретного имени",
        "Жезл разорванной реальности",
        "Посох тьмы между мирами",
        "Скипетр бесконечной дуги",
        "Лунный катаклизм",
        "Посох архитектора звёзд",
        "Жезл пожирателя света",
        "Скипетр нижних глубин",
        "Посох единого заклинания",
    ],
    [
        "Щит обсидианового дракона",
        "Эгида виверны",
        "Бастион кошмара",
        "Щит непоколебимой звезды",
        "Башня последнего стража",
        "Щит крушителя волн",
        "Эгида вечного заката",
        "Щит хранителя печати",
        "Зеркало судьбы",
        "Несокрушимость небес",
    ],
    [
        "Жезл белого огня",
        "Уголь судьбы",
        "Молния Арканы",
        "Игла между мирами",
        "Жезл абсолютной власти",
        "Пустота в стекле",
        "Созвездие в руке",
        "Разлом реальности",
        "Жезл последнего дня",
        "Первозданная искра",
    ],
    [
        "Дубина йотунов",
        "Булава карающего света",
        "Шар крушения башен",
        "Булава погибели",
        "Звезда кровавого рассвета",
        "Булава чистилища",
        "Шипы нижнего круга",
        "Булава небесных врат",
        "Булава из костей богов",
        "Вечная булава",
    ],
    [
        "Копьё первого удара",
        "Пика легиона теней",
        "Копьё туманных болот",
        "Спинтон вечной стражи",
        "Копьё бронзовой стены",
        "Пика драконьей чешуи",
        "Гром небесный",
        "Копьё безымянного героя",
        "Алебарда звёздного суда",
        "Копьё разорванного неба",
    ],
    [
        "Арбалет белого ворона",
        "Болт сквозь сталь",
        "Тяжесть осадной звезды",
        "Арбалет чёрной дуги",
        "Болт гарнизона мёртвых",
        "Осадный зверь",
        "Арбалет разорванной луны",
        "Серебро приговора",
        "Болт из нижнего мира",
        "Звёздный дождь болтов",
    ],
    [
        "Скипетр молчаливого ордена",
        "Жезл вечного посвящения",
        "Скипетр кровавого обряда",
        "Око за завесой",
        "Скипетр семи печатей",
        "Сияние погибшего солнца",
        "Скипетр последнего суда",
        "Культ разорванной ткани",
        "Скипетр избранного мёртвого",
        "Верховный жезл",
    ],
    [
        "Молот зари миров",
        "Крушитель небосклонов",
        "Молот казни титанов",
        "Падение великанов",
        "Молот бесконечной войны",
        "Громовержец бури",
        "Молот костяного трона",
        "Руны крушения",
        "Молот мёртвых богов",
        "Древо-молот",
    ],
    [
        "Сфера вечного льда",
        "Ядро мана-реактора",
        "Кристалл поглощённой звезды",
        "Око абсолютного фокуса",
        "Сфера цепной молнии",
        "Вихрь запретных имён",
        "Сфера семи наставлений",
        "Бездна в стеклянном шаре",
        "Сфера чёрного солнца",
        "Сфера первого слова",
    ],
]

NIGHT_TAGS = ("кошмара", "искажения", "заката", "руин", "безумия", "крови")
HELL_TAGS = ("преисподней", "бездны", "апокалипсиса", "вечности", "Тартара", "абсолюта")


def _armor_amulet_ring_name(base: str, grade: int, salt: int) -> str:
    if grade == 1:
        return f"{base} ({NIGHT_TAGS[salt % len(NIGHT_TAGS)]})"
    return f"{base} ({HELL_TAGS[salt % len(HELL_TAGS)]})"


def _restricted_grade_name(base: str, grade: int, salt: int) -> str:
    """Продвинутые/великолепные для предметов с требованием расы или класса."""
    if grade == 1:
        return f"{base} · возвыш. ({NIGHT_TAGS[salt % len(NIGHT_TAGS)]})"
    return f"{base} · апогей ({HELL_TAGS[salt % len(HELL_TAGS)]})"


def _scaled_int(v: int, mult: float) -> int:
    return max(0, int(round(float(v) * mult)))


def _scaled_speed(v: int, grade: int) -> int:
    if v <= 0:
        return v
    delta = 1 if grade == 1 else 2
    return max(2, int(v) - delta)


def _apply_grade_row(row: dict, grade: int, new_name: str, salt: int) -> dict:
    mult_dmg = 1.22 if grade == 1 else 1.48
    mult_armor = 1.14 if grade == 1 else 1.32
    mult_stat = 1.12 if grade == 1 else 1.28
    mult_price = 1.28 if grade == 1 else 1.65
    mult_sec = 1.10 if grade == 1 else 1.24
    off = 5 if grade == 1 else 10

    lm = int(row["level_min"]) + off
    lx = int(row["level_max"]) + off
    lx = min(60, lx)
    lm = min(lm, lx)

    out = {
        **row,
        "name": new_name,
        "base_grade": grade,
        "level_min": lm,
        "level_max": lx,
        "dmg_min": _scaled_int(int(row["dmg_min"] or 0), mult_dmg),
        "dmg_max": _scaled_int(int(row["dmg_max"] or 0), mult_dmg),
        "attack_speed": _scaled_speed(int(row["attack_speed"] or 0), grade),
        "armor_base": _scaled_int(int(row["armor_base"] or 0), mult_armor),
        "stat1_value": _scaled_int(int(row["stat1_value"] or 0), mult_stat),
        "stat2_value": _scaled_int(int(row["stat2_value"] or 0), mult_stat),
        "base_price": max(1, _scaled_int(int(row["base_price"] or 10), mult_price)),
        "weight": max(
            1,
            _scaled_int(int(row["weight"] or 100), 0.72 if grade == 1 else 0.48),
        ),
        "secondary_bonus_value": float(row["secondary_bonus_value"] or 0.0) * mult_sec,
        "fixed_bonus_type": row.get("fixed_bonus_type"),
        "fixed_bonus_value": float(row.get("fixed_bonus_value") or 0.0) * mult_sec,
        "required_race": row.get("required_race"),
        "required_class": row.get("required_class"),
    }
    return out


async def seed() -> None:
    init_engine()
    async for session in get_session():
        try:
            await session.execute(text("SELECT base_grade FROM item_base_templates LIMIT 1"))
        except Exception as e:
            print("Таблица или колонка base_grade недоступны. Выполните: alembic upgrade head")
            raise e

        await session.execute(text("DELETE FROM item_base_templates WHERE base_grade IN (1, 2)"))
        res = await session.execute(
            text(
                """
                SELECT
                    id, name, item_type, subtype, attack_type, tier, level_min, level_max,
                    dmg_min, dmg_max, attack_speed, armor_base,
                    stat1_type, stat1_value, stat2_type, stat2_value,
                    base_price, boss_allowed, weight,
                    secondary_bonus_type, secondary_bonus_value,
                    fixed_bonus_type, fixed_bonus_value,
                    required_race, required_class
                FROM item_base_templates
                WHERE COALESCE(base_grade, 0) = 0
                ORDER BY id
                """
            )
        )
        rows = [dict(r._mapping) for r in res.fetchall()]
        if not rows:
            print("Нет строк base_grade=0 — пропуск.")
            await session.commit()
            return

        insert_sql = text(
            """
            INSERT INTO item_base_templates (
                name, item_type, subtype, attack_type, tier, level_min, level_max,
                dmg_min, dmg_max, attack_speed, armor_base,
                stat1_type, stat1_value, stat2_type, stat2_value,
                base_price, boss_allowed, weight,
                secondary_bonus_type, secondary_bonus_value, base_grade,
                fixed_bonus_type, fixed_bonus_value,
                required_race, required_class
            ) VALUES (
                :name, :item_type, :subtype, :attack_type, :tier, :level_min, :level_max,
                :dmg_min, :dmg_max, :attack_speed, :armor_base,
                :stat1_type, :stat1_value, :stat2_type, :stat2_value,
                :base_price, :boss_allowed, :weight,
                :secondary_bonus_type, :secondary_bonus_value, :base_grade,
                :fixed_bonus_type, :fixed_bonus_value,
                :required_race, :required_class
            )
            """
        )

        for i, row in enumerate(rows):
            it = str(row["item_type"] or "").lower()
            wline = (
                _weapon_line_from_canon_name(str(row["name"] or ""), int(row["tier"] or 0))
                if it == "weapon"
                else None
            )
            tier_idx = int(row["tier"]) - 1
            salt = int(row["tier"]) + i * 7

            has_restrict = (row.get("required_race") is not None) or (row.get("required_class") is not None)
            if has_restrict:
                adv_name = _restricted_grade_name(str(row["name"]), 1, salt)
                mag_name = _restricted_grade_name(str(row["name"]), 2, salt + 3)
            elif wline is not None and 0 <= tier_idx < 10:
                adv_name = WEAPON_ADV[wline][tier_idx]
                mag_name = WEAPON_MAG[wline][tier_idx]
            else:
                adv_name = _armor_amulet_ring_name(str(row["name"]), 1, salt)
                mag_name = _armor_amulet_ring_name(str(row["name"]), 2, salt + 3)

            for g, nm in ((1, adv_name), (2, mag_name)):
                payload = _apply_grade_row(row, g, nm, salt)
                await session.execute(
                    insert_sql,
                    {
                        "name": payload["name"],
                        "item_type": payload["item_type"],
                        "subtype": payload["subtype"],
                        "attack_type": payload["attack_type"],
                        "tier": payload["tier"],
                        "level_min": payload["level_min"],
                        "level_max": payload["level_max"],
                        "dmg_min": payload["dmg_min"],
                        "dmg_max": payload["dmg_max"],
                        "attack_speed": payload["attack_speed"],
                        "armor_base": payload["armor_base"],
                        "stat1_type": payload["stat1_type"],
                        "stat1_value": payload["stat1_value"],
                        "stat2_type": payload["stat2_type"],
                        "stat2_value": payload["stat2_value"],
                        "base_price": payload["base_price"],
                        "boss_allowed": bool(payload["boss_allowed"]),
                        "weight": payload["weight"],
                        "secondary_bonus_type": payload["secondary_bonus_type"],
                        "secondary_bonus_value": payload["secondary_bonus_value"],
                        "fixed_bonus_type": payload.get("fixed_bonus_type"),
                        "fixed_bonus_value": payload.get("fixed_bonus_value"),
                        "base_grade": g,
                        "required_race": payload.get("required_race"),
                        "required_class": payload.get("required_class"),
                    },
                )

        await session.commit()

        n0 = await session.scalar(text("SELECT COUNT(*) FROM item_base_templates WHERE base_grade = 0"))
        n1 = await session.scalar(text("SELECT COUNT(*) FROM item_base_templates WHERE base_grade = 1"))
        n2 = await session.scalar(text("SELECT COUNT(*) FROM item_base_templates WHERE base_grade = 2"))
        print(f"item_base_templates: normal={n0}, advanced={n1}, magnificent={n2}")
        break


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
