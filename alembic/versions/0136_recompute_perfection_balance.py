"""Recompute perfection bonus history/totals after catalog rebalance.

Revision ID: 0136_recompute_perfection_balance
Revises: 0135_gd_daily_finale_image_config
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Sequence, Union

revision: str = "0136_recompute_perfection_balance"
down_revision: Union[str, None] = "0135_gd_daily_finale_image_config"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


async def _recompute() -> None:
    from waifu_bot.db.session import SessionLocal, init_engine
    from waifu_bot.services.perfection import recompute_all_perfection_from_catalog

    init_engine()
    assert SessionLocal is not None
    async with SessionLocal() as session:
        reports = await recompute_all_perfection_from_catalog(session, sync_hp=True)
        await session.commit()
        ice = next((r for r in reports if int(r["player_id"]) == 524710129), None)
        if ice:
            print(
                "0136 icefear totals:",
                ice.get("old_totals"),
                "->",
                ice.get("new_totals"),
                "hp_synced=",
                ice.get("hp_synced"),
            )
        print(f"0136 recomputed perfection for {len(reports)} player(s)")


def _run_recompute_in_fresh_loop() -> None:
    """Alembic async env already has a loop — run recompute in a worker thread."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(asyncio.run, _recompute())
        fut.result()


def upgrade() -> None:
    """Пересчитать value/totals/pending и sync HP по актуальному каталогу.

    Instant gold/dust/stones уже начисленные игрокам не откатываются.
    """
    _run_recompute_in_fresh_loop()


def downgrade() -> None:
    # Значения старого каталога не восстанавливаем автоматически.
    pass
