#!/usr/bin/env python3
"""Backfill items.name after splitting canonical vs legendary template names."""

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

DEFAULT_LEGENDARY_JSON = ROOT / "scripts/data/legendary_item_names_ru.json"


async def _run(*, dry_run: bool) -> int:
    from waifu_bot.db.session import get_session, init_engine

    data = json.loads(DEFAULT_LEGENDARY_JSON.read_text(encoding="utf-8"))
    llm_names = filter_template_id_keys(extract_names_map(data))
    if not llm_names:
        print("no LLM names in JSON")
        return 1

    llm_by_name = {name: int(tid) for tid, name in llm_names.items()}

    init_engine()
    updated = 0
    async for session in get_session():
        rows = (
            await session.execute(
                text(
                    """
                    SELECT i.id AS item_id,
                           i.name AS item_name,
                           inv.rarity AS rarity,
                           inv.is_legendary AS is_legendary
                    FROM items i
                    JOIN inventory_items inv ON inv.item_id = i.id
                    """
                )
            )
        ).mappings().all()

        for row in rows:
            item_name = str(row.get("item_name") or "").strip()
            if item_name not in llm_by_name:
                continue
            tid = llm_by_name[item_name]
            tpl = (
                await session.execute(
                    text(
                        """
                        SELECT name, legendary_name_ru
                        FROM item_base_templates
                        WHERE id = :id AND COALESCE(base_grade, 0) = 0
                        LIMIT 1
                        """
                    ),
                    {"id": tid},
                )
            ).mappings().first()
            if not tpl:
                continue
            is_leg = bool(row.get("is_legendary")) or int(row.get("rarity") or 0) >= 5
            if is_leg:
                new_name = str(tpl.get("legendary_name_ru") or tpl.get("name") or "").strip()
            else:
                new_name = str(tpl.get("name") or "").strip()
            if not new_name or new_name == item_name:
                continue
            if dry_run:
                print(f"  item {row['item_id']}: {item_name!r} -> {new_name!r}")
            else:
                await session.execute(
                    text("UPDATE items SET name = :name WHERE id = :id"),
                    {"name": new_name, "id": int(row["item_id"])},
                )
            updated += 1

        if not dry_run:
            await session.commit()
        break

    print(f"{'would update' if dry_run else 'updated'} {updated} item rows")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return asyncio.run(_run(dry_run=args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
