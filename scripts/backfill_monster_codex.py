#!/usr/bin/env python3
"""Ретро-бэкфилл бестиария (player_monster_codex) из истории боёв.

Восстанавливает счётчики убийств для существующих игроков на основе таблицы
``dungeon_run_monsters``: для каждого завершённого/идущего рана считаются монстры,
которые были пройдены (позиция меньше текущей) либо убиты (current_hp <= 0), и у
которых есть ``template_id``. Это даёт ветеранам стартовый прогресс в библиотеке,
вместо обнуления всего опыта.

Внимание: это приблизительная оценка (по пройденным комнатам), а не точный лог
каждого убийства. ``first_seen_at`` / ``first_kill_at`` ставятся в текущее время.

Запуск из корня репозитория (должен быть задан POSTGRES_DSN):
    python scripts/backfill_monster_codex.py            # реальный прогон
    python scripts/backfill_monster_codex.py --dry-run  # только показать статистику
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

# Ensure src/ is importable when run as a plain script.
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from waifu_bot.db.models.dungeon import (  # noqa: E402
    DungeonRun,
    DungeonRunMonster,
    PlayerMonsterCodex,
)
from waifu_bot.db.session import SessionLocal, init_engine  # noqa: E402


async def run(dry_run: bool) -> int:
    init_engine()
    assert SessionLocal is not None
    now = datetime.utcnow()

    async with SessionLocal() as session:
        # Count "killed" monsters per (player, template): a monster counts as
        # killed if its run advanced past its position OR its hp reached 0.
        stmt = (
            select(
                DungeonRun.player_id.label("player_id"),
                DungeonRunMonster.template_id.label("template_id"),
                func.count().label("kills"),
            )
            .join(DungeonRun, DungeonRun.id == DungeonRunMonster.run_id)
            .where(
                DungeonRunMonster.template_id.isnot(None),
                or_(
                    DungeonRunMonster.current_hp <= 0,
                    DungeonRunMonster.position < DungeonRun.current_position,
                ),
            )
            .group_by(DungeonRun.player_id, DungeonRunMonster.template_id)
        )
        rows = list((await session.execute(stmt)).all())
        print(f"Найдено пар (игрок, монстр): {len(rows)}")
        total_kills = sum(int(r.kills) for r in rows)
        print(f"Суммарно убийств для бэкфилла: {total_kills}")

        if dry_run:
            print("Dry-run: изменения не записаны.")
            return 0

        written = 0
        for r in rows:
            kills = int(r.kills or 0)
            if kills <= 0:
                continue
            # Only set the codex value if it would increase the current count, so
            # re-running the script is safe and never lowers real progress.
            stmt_up = (
                pg_insert(PlayerMonsterCodex)
                .values(
                    player_id=int(r.player_id),
                    monster_template_id=int(r.template_id),
                    kills=kills,
                    first_seen_at=now,
                    first_kill_at=now,
                    last_kill_at=now,
                )
                .on_conflict_do_update(
                    index_elements=["player_id", "monster_template_id"],
                    set_={"kills": func.greatest(PlayerMonsterCodex.kills, kills)},
                )
            )
            await session.execute(stmt_up)
            written += 1
        await session.commit()
        print(f"Записано/обновлено строк: {written}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill player_monster_codex from run history")
    ap.add_argument("--dry-run", action="store_true", help="Только показать статистику")
    args = ap.parse_args()
    return asyncio.run(run(args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
