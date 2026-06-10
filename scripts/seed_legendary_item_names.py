#!/usr/bin/env python3
"""Apply legendary_item_names_ru.json to item_base_templates.legendary_name_ru by id."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.lib.legendary_name_llm import extract_names_map, filter_template_id_keys  # noqa: E402

DEFAULT_IN = ROOT / "scripts/data/legendary_item_names_ru.json"


async def _run(in_path: Path, *, dry_run: bool) -> int:
    from waifu_bot.db.session import get_session, init_engine

    if not in_path.is_file():
        print(f"Missing {in_path}")
        return 1
    data = json.loads(in_path.read_text(encoding="utf-8"))
    raw_names = extract_names_map(data)
    names = filter_template_id_keys(raw_names)
    skipped = len(raw_names) - len(names)
    if skipped:
        print(f"skipped {skipped} non-template keys")
    if not names:
        print(f"no names to seed from {in_path}")
        return 0
    if dry_run:
        for tid in sorted(names)[:10]:
            print(f"  {tid}: {names[tid]}")
        if len(names) > 10:
            print(f"  ... and {len(names) - 10} more")
        print(f"dry-run: would update legendary_name_ru for {len(names)} templates")
        return 0

    init_engine()
    updated = 0
    async for session in get_session():
        for tid, name in names.items():
            await session.execute(
                text(
                    """
                    UPDATE item_base_templates
                    SET legendary_name_ru = :name
                    WHERE id = :id
                      AND COALESCE(base_grade, 0) = 0
                      AND cardinality(COALESCE(legendary_bonus_ids, '{}')) > 0
                    """
                ),
                {"name": name, "id": tid},
            )
            updated += 1
        await session.commit()
        break
    print(f"updated legendary_name_ru for {updated} templates from {in_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("in_path", nargs="?", type=Path, default=DEFAULT_IN)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return asyncio.run(_run(args.in_path, dry_run=args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
