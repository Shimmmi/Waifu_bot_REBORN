#!/usr/bin/env python3
"""Сбросить выбранные бонусы совершенствования и заново поставить очередь.

Не меняет perfection_level / perfection_experience.
Не откатывает instant gold/dust/stones. Дерево пассивок не трогает.

Usage:
  python scripts/reset_perfection_picks.py --player-id ID --claimed-opg N [--waifu-name NAME]
  python scripts/reset_perfection_picks.py --player-id ID --claimed-opg N --apply
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from waifu_bot.core.config import settings
from waifu_bot.db import models as m
from waifu_bot.services.perfection import reset_player_perfection_picks


async def main(
    player_id: int,
    claimed_opg: int,
    apply: bool,
    waifu_name: str | None,
) -> int:
    engine = create_async_engine(settings.postgres_dsn, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        player = await session.get(m.Player, int(player_id))
        if player is None:
            print(f"player {player_id} not found")
            await engine.dispose()
            return 1
        waifu = (
            await session.execute(
                select(m.MainWaifu).where(m.MainWaifu.player_id == int(player_id))
            )
        ).scalar_one_or_none()
        actual_name = str(getattr(waifu, "name", "") or "")
        if waifu_name and actual_name != waifu_name:
            print(
                json.dumps(
                    {
                        "error": "waifu_name_mismatch",
                        "expected": waifu_name,
                        "actual": actual_name,
                    },
                    ensure_ascii=False,
                )
            )
            await engine.dispose()
            return 1
        bonus_n = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(m.PlayerPerfectionBonus)
                    .where(m.PlayerPerfectionBonus.player_id == int(player_id))
                )
            ).scalar_one()
            or 0
        )
        pending_n = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(m.PlayerPerfectionPending)
                    .where(m.PlayerPerfectionPending.player_id == int(player_id))
                )
            ).scalar_one()
            or 0
        )
        before = {
            "player_id": int(player.id),
            "waifu_name": actual_name,
            "perfection_level": int(player.perfection_level or 0),
            "perfection_experience": int(player.perfection_experience or 0),
            "skill_points": int(player.skill_points or 0),
            "bonus_rows": bonus_n,
            "pending_rows": pending_n,
        }
        report = await reset_player_perfection_picks(
            session, player, claimed_skill_points=int(claimed_opg)
        )
        expected_pending = int(report["queued_bonus"]) + int(report["queued_skill_point"])
        after_pending = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(m.PlayerPerfectionPending)
                    .where(m.PlayerPerfectionPending.player_id == int(player_id))
                )
            ).scalar_one()
            or 0
        )
        print(
            json.dumps(
                {
                    "before": before,
                    "reset": report,
                    "pending_after": after_pending,
                    "expected_pending": expected_pending,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        if apply:
            await session.commit()
            print("applied")
        else:
            await session.rollback()
            print("dry-run; pass --apply to commit")
    await engine.dispose()
    return 0


if __name__ == "__main__":
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--player-id", type=int, required=True)
    parser.add_argument(
        "--claimed-opg",
        type=int,
        required=True,
        help="How many perfection milestone OPG were already claimed (subtract from free skill_points)",
    )
    parser.add_argument("--waifu-name", type=str, default=None)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    raise SystemExit(
        asyncio.run(
            main(args.player_id, args.claimed_opg, args.apply, args.waifu_name)
        )
    )
