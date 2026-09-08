#!/usr/bin/env python3
"""
Populate item_base_templates.base_grade 1 and 2 (продвинутый / великолепный).

Запуск после alembic upgrade (колонка base_grade):
  python scripts/seed_item_base_grades.py

Удаляет существующие строки с base_grade IN (1,2) и вставляет заново из base_grade=0.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import text

from waifu_bot.db.session import get_session, init_engine
from waifu_bot.game.item_grade_names import (
    HELL_TAGS,
    NIGHT_TAGS,
    WEAPON_ADV,
    WEAPON_MAG,
    weapon_line_from_canon_name,
)


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
                weapon_line_from_canon_name(str(row["name"] or ""), int(row["tier"] or 0))
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
