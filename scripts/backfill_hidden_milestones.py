#!/usr/bin/env python3
"""Тихий бэкфилл скрытых навыков-вех по текущей статистике игроков.

Не шлёт групповые анонсы и не пишет event_log.

Запуск из корня репозитория (нужен POSTGRES_DSN):
    python scripts/backfill_hidden_milestones.py --dry-run
    python scripts/backfill_hidden_milestones.py --apply
    python scripts/backfill_hidden_milestones.py --apply --player-id 123 --player-id 456
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from waifu_bot.core.config import settings
from waifu_bot.db.models import Player
from waifu_bot.services.hidden_milestones import MILESTONE_SKILL_IDS, sync_milestone_skills


async def _run(
    *,
    player_ids: list[int] | None,
    apply: bool,
    batch_size: int,
) -> int:
    engine = create_async_engine(settings.postgres_dsn, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    processed = 0
    offset = 0
    try:
        while True:
            async with Session() as session:
                q = select(Player.id).order_by(Player.id)
                if player_ids:
                    q = q.where(Player.id.in_(player_ids))
                q = q.offset(offset).limit(batch_size)
                ids = [int(x) for x in (await session.execute(q)).scalars().all()]
                if not ids:
                    break
                for pid in ids:
                    counters = await sync_milestone_skills(session, pid, silent=True)
                    nonzero = {k: v for k, v in counters.items() if int(v or 0) > 0}
                    print(f"player_id={pid} counters={nonzero or '{}'}")
                    processed += 1
                if apply:
                    await session.commit()
                else:
                    await session.rollback()
            offset += len(ids)
            if player_ids and offset >= len(player_ids):
                break
    finally:
        await engine.dispose()
    mode = "applied" if apply else "dry-run"
    print(f"{mode}: {processed} player(s), {len(MILESTONE_SKILL_IDS)} milestone skills")
    return 0


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Backfill hidden milestone skills")
    parser.add_argument("--player-id", type=int, action="append", default=None)
    parser.add_argument("--apply", action="store_true", help="Commit changes (default is dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="Do not commit (default)")
    parser.add_argument("--batch-size", type=int, default=200)
    args = parser.parse_args()
    apply = bool(args.apply) and not bool(args.dry_run)
    return asyncio.run(
        _run(player_ids=args.player_id, apply=apply, batch_size=max(1, int(args.batch_size)))
    )


if __name__ == "__main__":
    raise SystemExit(main())
