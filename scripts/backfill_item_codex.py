#!/usr/bin/env python3
"""Backfill player_item_codex and player_affix_codex from existing inventory and shop offers.

Запуск из корня репозитория (нужен POSTGRES_DSN или DATABASE_URL):
    python scripts/backfill_item_codex.py
    python scripts/backfill_item_codex.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select

from waifu_bot.db.models import InventoryItem, ShopOffer
from waifu_bot.db.session import SessionLocal, init_engine
from waifu_bot.services.item_codex import register_inventory_codex


async def run(dry_run: bool) -> int:
    init_engine()
    assert SessionLocal is not None

    item_rows = 0
    offer_rows = 0

    async with SessionLocal() as session:
        inv_ids: set[int] = set()
        player_by_inv: dict[int, int] = {}

        inv_q = await session.execute(
            select(InventoryItem).where(InventoryItem.player_id.isnot(None))
        )
        for inv in inv_q.scalars().all():
            if inv.id and inv.player_id:
                inv_ids.add(int(inv.id))
                player_by_inv[int(inv.id)] = int(inv.player_id)

        offer_q = await session.execute(select(ShopOffer))
        for off in offer_q.scalars().all():
            if off.inventory_item_id and off.player_id:
                inv_ids.add(int(off.inventory_item_id))
                player_by_inv[int(off.inventory_item_id)] = int(off.player_id)

        print(f"Уникальных inventory_items для кодекса: {len(inv_ids)}")

        if dry_run:
            print("Dry-run: изменения не записаны.")
            return 0

        for iid in sorted(inv_ids):
            inv = await session.get(InventoryItem, iid)
            pid = player_by_inv.get(iid)
            if inv is None or not pid:
                continue
            if inv.player_id is not None:
                item_rows += 1
            else:
                offer_rows += 1
            await register_inventory_codex(session, pid, inv)

        await session.commit()
        print(f"Обработано строк инвентаря игрока: {item_rows}")
        print(f"Обработано офферов магазина (без player_id на предмете): {offer_rows}")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill item/affix library codex")
    ap.add_argument("--dry-run", action="store_true", help="Только статистика")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(run(args.dry_run)))


if __name__ == "__main__":
    main()
