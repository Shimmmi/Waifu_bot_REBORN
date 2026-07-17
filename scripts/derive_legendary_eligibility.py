#!/usr/bin/env python3
"""Derive and optionally apply drop eligibility columns on legendary_bonuses."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import text

from waifu_bot.db.session import SessionLocal, init_engine
from waifu_bot.game.legendary_bonuses.eligibility import derive_drop_eligibility


async def _run(*, apply: bool, export: Path | None) -> None:
    init_engine()
    assert SessionLocal is not None
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT id, bonus_key, trigger_group, params, is_active
                    FROM legendary_bonuses
                    ORDER BY id
                    """
                )
            )
        ).mappings().all()

        updates: list[dict] = []
        for row in rows:
            bonus = dict(row)
            elig = derive_drop_eligibility(bonus)
            updates.append(
                {
                    "id": int(bonus["id"]),
                    "bonus_key": bonus["bonus_key"],
                    **elig,
                }
            )

        if export:
            export.write_text(json.dumps(updates, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Wrote {len(updates)} rows to {export}")

        if apply:
            for u in updates:
                await session.execute(
                    text(
                        """
                        UPDATE legendary_bonuses
                        SET min_item_tier = :min_item_tier,
                            max_item_tier = :max_item_tier,
                            allowed_slot_types = :allowed_slot_types,
                            is_drop_enabled = :is_drop_enabled
                        WHERE id = :id
                        """
                    ),
                    {
                        "id": u["id"],
                        "min_item_tier": u["min_item_tier"],
                        "max_item_tier": u["max_item_tier"],
                        "allowed_slot_types": u["allowed_slot_types"],
                        "is_drop_enabled": u["is_drop_enabled"],
                    },
                )
            await session.commit()
            print(f"Applied eligibility to {len(updates)} legendary bonuses")
        elif not export:
            for u in updates[:5]:
                print(u)
            print(f"... total {len(updates)} bonuses")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write updates to DB")
    parser.add_argument("--export", type=Path, help="Export JSON snapshot")
    args = parser.parse_args()
    asyncio.run(_run(apply=args.apply, export=args.export))


if __name__ == "__main__":
    main()
