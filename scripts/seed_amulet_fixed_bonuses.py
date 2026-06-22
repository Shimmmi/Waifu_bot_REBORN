#!/usr/bin/env python3
"""Apply or verify amulet fixed bonus updates from amulet_bonus_matrix_draft.json."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.amulet_bonus_seed import (  # noqa: E402
    DEFAULT_JSON,
    generate_migration_sql,
    iter_updates,
    load_profiles,
)
from sqlalchemy import text

from waifu_bot.db.session import get_session, init_engine  # noqa: E402

DEFAULT_SQL_OUT = ROOT / "info" / "amulet_bonus_migration.sql"


async def apply_updates(dry_run: bool = False) -> int:
    updates = iter_updates()
    init_engine()
    async for session in get_session():
        for row in updates:
            sql = text(
                """
                UPDATE item_base_templates
                SET secondary_bonus_type = :sec_type,
                    secondary_bonus_value = :sec_val,
                    fixed_bonus_type = :fix_type,
                    fixed_bonus_value = :fix_val
                WHERE name = :name AND tier = :tier
                  AND item_type = 'amulet'
                  AND COALESCE(base_grade, 0) = 0
                """
            )
            if dry_run:
                continue
            await session.execute(
                sql,
                {
                    "name": row["name"],
                    "tier": row["tier"],
                    "sec_type": row["secondary_bonus_type"],
                    "sec_val": row["secondary_bonus_value"],
                    "fix_type": row["fixed_bonus_type"],
                    "fix_val": row["fixed_bonus_value"],
                },
            )
        if not dry_run:
            await session.commit()
        return len(updates)
    return 0


async def verify() -> int:
    updates = iter_updates()
    init_engine()
    errors: list[str] = []
    async for session in get_session():
        for row in updates:
            res = await session.execute(
                text(
                    """
                    SELECT secondary_bonus_type, secondary_bonus_value,
                           fixed_bonus_type, fixed_bonus_value
                    FROM item_base_templates
                    WHERE name = :name AND tier = :tier
                      AND item_type = 'amulet'
                      AND COALESCE(base_grade, 0) = 0
                    """
                ),
                {"name": row["name"], "tier": row["tier"]},
            )
            db = res.mappings().first()
            if not db:
                errors.append(f"missing template {row['name']} T{row['tier']}")
                continue
            for key in ("secondary_bonus_type", "fixed_bonus_type"):
                exp = row[key]
                got = db[key]
                if exp != got:
                    errors.append(f"{row['name']} T{row['tier']}: {key} {got!r} != {exp!r}")
            for key in ("secondary_bonus_value", "fixed_bonus_value"):
                exp = float(row[key] or 0)
                got = float(db[key] or 0)
                if abs(exp - got) > 0.002:
                    errors.append(f"{row['name']} T{row['tier']}: {key} {got} != {exp}")
        break
    if errors:
        print("VERIFY FAILED:")
        for e in errors:
            print(" ", e)
        return 1
    print(f"OK: {len(updates)} amulet templates verified")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Apply updates to DB")
    parser.add_argument("--verify", action="store_true", help="Verify DB matches JSON")
    parser.add_argument("--generate-sql", action="store_true", help="Write info/amulet_bonus_migration.sql")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--out", type=Path, default=DEFAULT_SQL_OUT)
    args = parser.parse_args()

    if args.generate_sql:
        args.out.write_text(generate_migration_sql(args.json), encoding="utf-8")
        print(f"Wrote {args.out}")
        return

    profiles = load_profiles(args.json)
    print(f"Loaded {len(profiles)} amulet profiles from {args.json}")

    if args.verify:
        raise SystemExit(asyncio.run(verify()))

    if args.apply:
        n = asyncio.run(apply_updates(dry_run=False))
        print(f"Applied {n} updates")
        raise SystemExit(asyncio.run(verify()))

    parser.print_help()


if __name__ == "__main__":
    main()
