#!/usr/bin/env python3
"""Export main_waifu portrait/paperdoll base64 from DB to static/game/waifus/*.webp."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from sqlalchemy import select

from waifu_bot.db.models import MainWaifu
from waifu_bot.db.session import get_session, init_engine
from waifu_bot.services.waifu_media_service import (
    paperdoll_file_path,
    portrait_file_path,
    sync_main_waifu_paperdoll_to_static,
    sync_main_waifu_portrait_to_static,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def run(*, dry_run: bool, force: bool) -> int:
    init_engine()
    portrait_n = 0
    paperdoll_n = 0
    async for session in get_session():
        rows = (await session.execute(select(MainWaifu))).scalars().all()
        for mw in rows:
            pid = int(mw.player_id)
            if getattr(mw, "image_data", None):
                need = force or not portrait_file_path(pid).is_file()
                if need:
                    if dry_run:
                        logger.info("[dry-run] portrait player_id=%s", pid)
                    elif sync_main_waifu_portrait_to_static(mw):
                        logger.info("portrait player_id=%s rev=%s", pid, mw.portrait_revision)
                    portrait_n += 1

            if getattr(mw, "paperdoll_image_data", None):
                need = force or not paperdoll_file_path(pid).is_file()
                if need:
                    if dry_run:
                        logger.info("[dry-run] paperdoll player_id=%s", pid)
                    elif sync_main_waifu_paperdoll_to_static(mw):
                        logger.info("paperdoll player_id=%s rev=%s", pid, mw.paperdoll_revision)
                    paperdoll_n += 1

        if not dry_run:
            await session.commit()
        break

    logger.info(
        "Done: %s portraits, %s paperdolls (%s)",
        portrait_n,
        paperdoll_n,
        "dry-run" if dry_run else "committed",
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="List rows only, no writes")
    parser.add_argument("--force", action="store_true", help="Overwrite existing webp files")
    args = parser.parse_args()
    return asyncio.run(run(dry_run=args.dry_run, force=args.force))


if __name__ == "__main__":
    raise SystemExit(main())
