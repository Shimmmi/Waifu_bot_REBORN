#!/usr/bin/env python3
"""Backfill bot_group_chats (no typer — same path setup as run_migrate.py)."""
from __future__ import annotations

import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))
venv_site = os.path.join(ROOT, ".venv", "lib", "python3.12", "site-packages")
if os.path.isdir(venv_site):
    sys.path.insert(0, venv_site)
dist = "/usr/local/lib/python3.12/dist-packages"
if os.path.isdir(dist):
    sys.path.insert(0, dist)


async def _main() -> None:
    from waifu_bot.db.session import get_session, init_engine
    from waifu_bot.services.bot_group_chats import backfill_bot_group_chats
    from waifu_bot.services.webhook import get_bot

    init_engine()
    bot = get_bot()
    async for session in get_session():
        result = await backfill_bot_group_chats(session, bot)
        print(result)
        break


if __name__ == "__main__":
    asyncio.run(_main())
