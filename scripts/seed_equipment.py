import json
from pathlib import Path

from sqlalchemy import select

from waifu_bot.db.session import get_session, init_engine
from waifu_bot.db import models as m

DATA_DIR = Path(__file__).resolve().parent / "data"
ITEMS_FILE = DATA_DIR / "item_templates.json"
AFFIXES_FILE = DATA_DIR / "affixes.json"


async def upsert_item_templates(session, items: list[dict]):
    for item in items:
        existing = await session.scalar(select(m.ItemTemplate).where(m.ItemTemplate.name == item["name"]))
        if existing:
            for k, v in item.items():
                setattr(existing, k, v)
        else:
            session.add(m.ItemTemplate(**item))


async def upsert_affixes(session, affixes: list[dict]):
    for aff in affixes:
        # normalize applies_to to list[str]
        applies = aff.get("applies_to") or []
        if isinstance(applies, dict):
            applies = applies.get("tags", [])
        aff["applies_to"] = applies
        existing = await session.scalar(select(m.Affix).where(m.Affix.name == aff["name"]))
        if existing:
            for k, v in aff.items():
                setattr(existing, k, v)
        else:
            session.add(m.Affix(**aff))


async def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    items = json.loads(ITEMS_FILE.read_text()) if ITEMS_FILE.exists() else []
    affixes = json.loads(AFFIXES_FILE.read_text()) if AFFIXES_FILE.exists() else []

    init_engine()
    async for session in get_session():
        await upsert_item_templates(session, items)
        await upsert_affixes(session, affixes)
        await session.commit()
        break
    print(f"Seeded items: {len(items)}, affixes: {len(affixes)}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())

