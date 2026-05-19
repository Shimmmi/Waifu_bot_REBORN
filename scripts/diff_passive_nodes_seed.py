#!/usr/bin/env python3
"""Compare passive_skill_nodes in DB to the seed in alembic 0037.

Without DB: prints parsed seed (count + ids/effect_types) from the migration file.

With --dsn: compares id, effect_type, effect_values JSON to the seed and prints mismatches.

Example:
  python scripts/diff_passive_nodes_seed.py
  POSTGRES_DSN=postgresql+asyncpg://... python scripts/diff_passive_nodes_seed.py --dsn "$POSTGRES_DSN"
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIG = ROOT / "alembic" / "versions" / "0037_passive_skill_tree.py"


def _load_seed_from_migration() -> list[tuple]:
    text = MIG.read_text(encoding="utf-8")
    m = re.search(
        r"_PASSIVE_NODES:\s*list\[tuple\]\s*=\s*(\[.*?\])\s*\n\n\s*def upgrade",
        text,
        re.S,
    )
    if not m:
        print("Could not parse _PASSIVE_NODES from migration.", file=sys.stderr)
        sys.exit(1)
    return ast.literal_eval(m.group(1))


def _seed_maps(rows: list[tuple]) -> tuple[dict[str, tuple[str, list]], set[str]]:
    """id -> (effect_type, effect_values list), set of ids."""
    by_id: dict[str, tuple[str, list]] = {}
    for row in rows:
        nid = str(row[0])
        et = str(row[8])
        ev = list(row[9]) if isinstance(row[9], (list, tuple)) else row[9]
        by_id[nid] = (et, ev)
    return by_id, set(by_id.keys())


async def _compare_db(dsn: str, seed_by_id: dict[str, tuple[str, list]], seed_ids: set[str]) -> int:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(dsn)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT id, effect_type, effect_values FROM passive_skill_nodes ORDER BY id")
            )
            db_rows = result.mappings().all()
    finally:
        await engine.dispose()

    db_ids = {str(r["id"]) for r in db_rows}
    extra = db_ids - seed_ids
    missing = seed_ids - db_ids
    if extra:
        print(f"DB has {len(extra)} id(s) not in seed: {sorted(extra)}")
    if missing:
        print(f"Seed has {len(missing)} id(s) missing in DB: {sorted(missing)}")

    mismatches = 0
    for r in db_rows:
        nid = str(r["id"])
        if nid not in seed_by_id:
            continue
        et_exp, ev_exp = seed_by_id[nid]
        et_db = str(r["effect_type"])
        ev_db = r["effect_values"]
        if isinstance(ev_db, str):
            try:
                ev_db = json.loads(ev_db)
            except json.JSONDecodeError:
                pass
        if et_db != et_exp:
            print(f"id={nid}: effect_type DB={et_db!r} seed={et_exp!r}")
            mismatches += 1
        if ev_db != ev_exp:
            print(f"id={nid}: effect_values DB={ev_db!r} seed={ev_exp!r}")
            mismatches += 1

    if not extra and not missing and mismatches == 0:
        print("DB matches seed (ids, effect_type, effect_values).")
        return 0
    return 1 if extra or missing or mismatches else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--dsn",
        help="Async SQLAlchemy URL (e.g. postgresql+asyncpg://user:pass@host/db)",
    )
    args = ap.parse_args()

    rows = _load_seed_from_migration()
    seed_by_id, seed_ids = _seed_maps(rows)
    print(f"Seed ({MIG.name}): {len(rows)} nodes")
    print("ids:", ", ".join(sorted(seed_ids)))

    if not args.dsn:
        return 0

    return asyncio.run(_compare_db(args.dsn, seed_by_id, seed_ids))


if __name__ == "__main__":
    raise SystemExit(main())
