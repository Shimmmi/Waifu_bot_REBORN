#!/usr/bin/env python3
"""Apply scripts/data/item_base_flavor_ru.json to item_base_templates.flavor_ru.

Запуск из корня репозитория (нужен POSTGRES_DSN или DATABASE_URL):
    python3 scripts/seed_item_base_flavor.py

После миграции:
    alembic upgrade head
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import text

from waifu_bot.db.session import get_session, init_engine
FLAVOR_FILE = ROOT / "scripts" / "data" / "item_base_flavor_ru.json"


async def main() -> None:
    raw = json.loads(FLAVOR_FILE.read_text(encoding="utf-8"))
    init_engine()
    updated = 0
    async for session in get_session():
        for key, flavor in raw.items():
            tid = int(key)
            txt = str(flavor or "").strip()
            if not txt:
                continue
            res = await session.execute(
                text("UPDATE item_base_templates SET flavor_ru = :f WHERE id = :id"),
                {"f": txt, "id": tid},
            )
            updated += int(res.rowcount or 0)
        await session.commit()
        break
    print(f"Updated flavor_ru for {updated} templates")


if __name__ == "__main__":
    asyncio.run(main())
