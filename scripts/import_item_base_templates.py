import asyncio
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select, text

from waifu_bot.db import models as m
from waifu_bot.db.session import get_session, init_engine


STAT_MAP: dict[str, str] = {
    "STR": "strength",
    "DEX": "agility",
    "INT": "intelligence",
    "VIT": "endurance",
    "CHA": "charm",
    "LUK": "luck",
}


@dataclass
class RawBase:
    id: int
    name: str
    item_type: str
    subtype: str
    attack_type: str | None
    tier: int
    level_min: int
    level_max: int
    dmg_min: int
    dmg_max: int
    attack_speed: int
    armor_base: int
    stat1_type: str | None
    stat1_value: int
    stat2_type: str | None
    stat2_value: int
    required_race: int | None
    required_class: int | None


def _slot_type(item_type: str, subtype: str) -> str:
    it = (item_type or "").lower()
    st = (subtype or "").lower()
    if it == "weapon":
        if st in {"one_hand"}:
            return "weapon_1h"
        if st in {"two_hand", "bow", "staff"}:
            return "weapon_2h"
        if st in {"offhand", "orb"}:
            return "offhand"
    if it == "armor":
        return "costume"
    if it == "ring":
        return "ring"
    if it == "amulet":
        return "amulet"
    return "other"


def _weapon_type(item_type: str, subtype: str, name: str) -> str | None:
    if (item_type or "").lower() != "weapon":
        return None
    st = (subtype or "").lower()
    nm = (name or "").lower()
    if st == "bow":
        return "bow"
    if st == "staff":
        return "staff"
    if st == "orb":
        return "orb"
    if st == "offhand":
        return "shield"
    if st == "one_hand" and any(k in nm for k in ("жезл", "скипетр")):
        return "staff"
    if any(k in nm for k in ("копьё", "копье", "пика", "алебарда", "спинтон")):
        return "sword"
    # melee 1h/2h — порядок важен: молот/булавы, топор/секира, затем явный меч, затем кинжальная линейка.
    if any(k in nm for k in ("молот", "булава", "дубина", "утренняя звезда", "шипастый шар")):
        return "axe"
    if any(k in nm for k in ("топор", "секира", "бердыш", "тесак", "колун")):
        return "axe"
    if any(
        k in nm
        for k in (
            "меч",
            "сворд",
            "катана",
            "клеймор",
            "палаш",
            "фламберг",
            "цвайхандер",
            "экскалибур",
            "сабля",
            "клейбарг",
            "вакидзаси",
        )
    ):
        return "sword"
    if any(
        k in nm
        for k in (
            "кинжал",
            "нож",
            "фальшион",
            "гладиус",
            "кортик",
            "жало",
            "стилет",
            "танто",
            "спата",
            "крис",
            "секач",
            "игла",
            "клык",
            "клинок",
        )
    ):
        return "dagger"
    return "weapon"


def _attack_type(attack_type: str | None) -> str | None:
    at = (attack_type or "").lower() or None
    if at in {"melee", "ranged", "magic"}:
        return at
    return None


def _implicit_effects(row: RawBase) -> dict:
    eff: dict[str, int | str] = {}
    if row.dmg_min > 0 or row.dmg_max > 0:
        eff["damage_min"] = int(row.dmg_min)
        eff["damage_max"] = int(row.dmg_max)
        if row.attack_speed:
            eff["attack_speed"] = int(row.attack_speed)
    if row.armor_base > 0:
        eff["armor_base"] = int(row.armor_base)
    if row.stat1_type:
        eff["base_stat"] = STAT_MAP.get(row.stat1_type, row.stat1_type)
        eff["base_stat_value"] = int(row.stat1_value)
    return eff


async def _ensure_item_base_templates_loaded(session) -> None:
    """
    Ensure that item_base_templates table from info/item_base_templates_import.sql
    exists and is populated, executing the SQL via the existing async engine
    instead of calling psql.
    """
    try:
        # If table exists and has rows, do nothing.
        res = await session.execute(text("SELECT COUNT(*) FROM item_base_templates"))
        count = int(res.scalar_one() or 0)
        if count > 0:
            return
    except Exception:
        # Table does not exist yet, will be created by the SQL file below.
        pass

    project_root = Path(__file__).resolve().parents[1]
    sql_path = project_root / "info" / "item_base_templates_import.sql"
    sql_text = sql_path.read_text(encoding="utf-8")

    # asyncpg does not allow multi-statement prepared execution, so we run the file
    # statement-by-statement. This SQL file is intentionally simple (no DO $$ blocks).
    cleaned_lines: list[str] = []
    for ln in sql_text.splitlines():
        s = ln.strip()
        if not s:
            continue
        # skip SQL comments
        if s.startswith("--"):
            continue
        cleaned_lines.append(ln)
    cleaned = "\n".join(cleaned_lines)

    # Drop transaction wrappers and verification SELECT - we control transactions via the session.
    cleaned = cleaned.replace("BEGIN;", "").replace("COMMIT;", "")
    cleaned = cleaned.replace("BEGIN ;", "").replace("COMMIT ;", "")

    statements = [s.strip() for s in cleaned.split(";") if s.strip()]
    for stmt in statements:
        # Skip verification query from the import file.
        if stmt.lower().startswith("select item_type") or stmt.lower().startswith("select"):
            continue
        await session.execute(text(stmt))
    await session.commit()


async def _fetch_raw_bases(session) -> list[RawBase]:
    # Use plain text query to avoid adding a model for item_base_templates.
    sql = text(
        """
        SELECT
            id,
            name,
            item_type,
            subtype,
            attack_type,
            tier,
            level_min,
            level_max,
            dmg_min,
            dmg_max,
            attack_speed,
            armor_base,
            stat1_type,
            stat1_value,
            stat2_type,
            stat2_value,
            required_race,
            required_class
        FROM item_base_templates
        WHERE COALESCE(base_grade, 0) = 0
        ORDER BY id
        """
    )
    res = await session.execute(sql)
    rows: list[RawBase] = []
    for r in res.fetchall():
        rows.append(
            RawBase(
                id=int(r.id),
                name=str(r.name),
                item_type=str(r.item_type),
                subtype=str(r.subtype),
                attack_type=str(r.attack_type) if r.attack_type is not None else None,
                tier=int(r.tier),
                level_min=int(r.level_min),
                level_max=int(r.level_max),
                dmg_min=int(r.dmg_min),
                dmg_max=int(r.dmg_max),
                attack_speed=int(r.attack_speed),
                armor_base=int(r.armor_base),
                stat1_type=str(r.stat1_type) if r.stat1_type is not None else None,
                stat1_value=int(r.stat1_value),
                stat2_type=str(r.stat2_type) if r.stat2_type is not None else None,
                stat2_value=int(r.stat2_value),
                required_race=int(r.required_race) if r.required_race is not None else None,
                required_class=int(r.required_class) if r.required_class is not None else None,
            )
        )
    return rows


async def upsert_item_bases_from_templates() -> None:
    init_engine()
    async for session in get_session():
        await _ensure_item_base_templates_loaded(session)

        raw_bases = await _fetch_raw_bases(session)
        existing = {
            b.base_id: b
            for b in (
                await session.execute(select(m.ItemBase))
            ).scalars().all()
        }

        for rb in raw_bases:
            base_id = f"tpl_{rb.id}"
            slot_type = _slot_type(rb.item_type, rb.subtype)
            weapon_type = _weapon_type(rb.item_type, rb.subtype, rb.name)
            atk_type = _attack_type(rb.attack_type)
            tags = {"tier": int(rb.tier)}
            reqs: dict[str, int] = {"level": int(rb.level_min)}
            if rb.required_race is not None:
                reqs["waifu_race"] = int(rb.required_race)
            if rb.required_class is not None:
                reqs["waifu_class"] = int(rb.required_class)
            implicit = _implicit_effects(rb)

            if base_id in existing:
                base = existing[base_id]
                base.name_ru = rb.name
                base.slot_type = slot_type
                base.weapon_type = weapon_type
                base.attack_type = atk_type
                base.tags = tags
                base.requirements = reqs
                base.implicit_effects = implicit
                base.base_level_min = int(rb.level_min)
                base.base_level_max = int(rb.level_max)
            else:
                session.add(
                    m.ItemBase(
                        base_id=base_id,
                        name_ru=rb.name,
                        slot_type=slot_type,
                        weapon_type=weapon_type,
                        attack_type=atk_type,
                        tags=tags,
                        requirements=reqs,
                        implicit_effects=implicit,
                        base_level_min=int(rb.level_min),
                        base_level_max=int(rb.level_max),
                    )
                )

        await session.commit()
        return


async def main() -> None:
    await upsert_item_bases_from_templates()


if __name__ == "__main__":
    asyncio.run(main())


