import json
from pathlib import Path

from sqlalchemy import select

from waifu_bot.db.session import get_session, init_engine
from waifu_bot.db import models as m


DATA_DIR = Path(__file__).resolve().parent / "data"
BASES_FILE = DATA_DIR / "diablo_item_bases.json"
FAMILIES_FILE = DATA_DIR / "diablo_affix_families.json"
TIERS_FILE = DATA_DIR / "diablo_affix_family_tiers.json"


async def upsert_item_bases(session, rows: list[dict]):
    for row in rows:
        base_id = row["base_id"]
        existing = await session.scalar(select(m.ItemBase).where(m.ItemBase.base_id == base_id))
        if existing:
            for k, v in row.items():
                setattr(existing, k, v)
        else:
            session.add(m.ItemBase(**row))


async def upsert_affix_families(session, rows: list[dict]):
    for row in rows:
        family_id = row["family_id"]
        existing = await session.scalar(select(m.AffixFamily).where(m.AffixFamily.family_id == family_id))
        if existing:
            for k, v in row.items():
                setattr(existing, k, v)
        else:
            session.add(m.AffixFamily(**row))


async def upsert_affix_family_tiers(session, rows: list[dict]):
    """
    Input rows use string family_id (AffixFamily.family_id).
    This function resolves it to numeric FK AffixFamily.id.
    """
    for row in rows:
        family_key = row["family_id"]
        family = await session.scalar(select(m.AffixFamily).where(m.AffixFamily.family_id == family_key))
        if not family:
            raise RuntimeError(f"AffixFamily not found for family_id={family_key}")

        affix_tier = int(row["affix_tier"])
        existing = await session.scalar(
            select(m.AffixFamilyTier).where(
                m.AffixFamilyTier.family_id == family.id,
                m.AffixFamilyTier.affix_tier == affix_tier,
            )
        )

        payload = dict(row)
        payload["family_id"] = family.id  # replace string key with FK

        if existing:
            for k, v in payload.items():
                setattr(existing, k, v)
        else:
            session.add(m.AffixFamilyTier(**payload))


async def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    bases = json.loads(BASES_FILE.read_text()) if BASES_FILE.exists() else []
    families = json.loads(FAMILIES_FILE.read_text()) if FAMILIES_FILE.exists() else []
    tiers = json.loads(TIERS_FILE.read_text()) if TIERS_FILE.exists() else []

    init_engine()
    async for session in get_session():
        await upsert_item_bases(session, bases)
        await upsert_affix_families(session, families)
        await session.flush()
        await upsert_affix_family_tiers(session, tiers)
        await session.commit()
        break

    print(f"Seeded item_bases={len(bases)}, affix_families={len(families)}, affix_family_tiers={len(tiers)}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())

