#!/usr/bin/env python3
"""Apply legendary_static_affixes JSON to item_base_templates."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IN = ROOT / "scripts/data/legendary_static_affixes.json"


async def _run(in_path: Path) -> int:
    from waifu_bot.db.session import get_session, init_engine

    if not in_path.is_file():
        print(f"Missing {in_path}")
        return 1
    data = json.loads(in_path.read_text(encoding="utf-8"))
    profiles = data.get("profiles") or data
    init_engine()
    updated = 0
    async for session in get_session():
        for tid, affixes in profiles.items():
            await session.execute(
                text(
                    """
                    UPDATE item_base_templates
                    SET legendary_static_affixes = CAST(:payload AS json)
                    WHERE id = :id AND COALESCE(base_grade, 0) = 0
                    """
                ),
                {"payload": json.dumps(affixes, ensure_ascii=False), "id": int(tid)},
            )
            updated += 1
        await session.commit()
        break
    print(f"updated {updated} templates from {in_path}")
    return 0


def main() -> int:
    in_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_IN
    return asyncio.run(_run(in_path))


if __name__ == "__main__":
    raise SystemExit(main())
