#!/usr/bin/env python3
"""Пересчитать бонусы совершенствования по актуальному каталогу.

Usage:
  python scripts/recompute_perfection_bonuses.py [--player-id ID ...] [--apply]

Без --apply — dry-run (отчёт old→new totals, без commit).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from waifu_bot.core.config import settings
from waifu_bot.db import models as m
from waifu_bot.services.perfection import recompute_player_perfection_from_catalog


async def main(player_ids: list[int] | None, apply: bool) -> int:
    engine = create_async_engine(settings.postgres_dsn, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        q = select(m.Player).where(m.Player.perfection_level > 0)
        if player_ids:
            q = q.where(m.Player.id.in_(player_ids))
        players = list((await session.execute(q)).scalars().all())
        if not players:
            print("no players with perfection_level > 0")
            await engine.dispose()
            return 0
        for player in players:
            report = await recompute_player_perfection_from_catalog(
                session, player, sync_hp=apply
            )
            print(
                json.dumps(
                    {
                        "player_id": report["player_id"],
                        "history_rows": report["history_rows"],
                        "pending_updated": report["pending_updated"],
                        "old_totals": report["old_totals"],
                        "new_totals": report["new_totals"],
                        "hp_synced": report["hp_synced"],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        if apply:
            await session.commit()
            print(f"applied: {len(players)} player(s)")
        else:
            await session.rollback()
            print(f"dry-run: {len(players)} player(s); pass --apply to commit")
    await engine.dispose()
    return 0


if __name__ == "__main__":
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--player-id", type=int, action="append", default=None)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.player_id, args.apply)))
