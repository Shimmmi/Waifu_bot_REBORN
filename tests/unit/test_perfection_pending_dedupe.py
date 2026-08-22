"""Perfection pending enqueue is unique per (player, kind, level)."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from waifu_bot.services.perfection import (
    _enqueue_pending,
    reset_player_perfection_picks,
)


def test_enqueue_pending_skips_duplicate_kind_and_level():
    async def _run():
        existing = SimpleNamespace(id=9, player_id=1, kind="bonus", perfection_level=10)
        session = AsyncMock()
        found = MagicMock()
        found.scalar_one_or_none.return_value = existing
        session.execute = AsyncMock(return_value=found)
        session.add = MagicMock()
        row = await _enqueue_pending(
            session, 1, kind="bonus", perfection_level=10, offer=[{"bonus_id": "x"}]
        )
        assert row is existing
        session.add.assert_not_called()
        session.flush.assert_not_called()

    asyncio.run(_run())


def test_enqueue_pending_inserts_when_absent():
    async def _run():
        session = AsyncMock()
        empty = MagicMock()
        empty.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=empty)
        session.flush = AsyncMock()
        session.add = MagicMock()
        row = await _enqueue_pending(
            session, 1, kind="skill_point", perfection_level=10, offer=[]
        )
        session.add.assert_called_once()
        added = session.add.call_args[0][0]
        assert added.player_id == 1
        assert added.kind == "skill_point"
        assert added.perfection_level == 10
        assert row is added
        session.flush.assert_awaited()

    asyncio.run(_run())


def test_reset_player_perfection_picks_subtracts_opg_and_requeues():
    async def _run():
        player = SimpleNamespace(
            id=7,
            perfection_level=11,
            skill_points=2,
            perfection_bonus_totals={"hp_flat": 300.0},
        )
        session = AsyncMock()
        session.execute = AsyncMock()
        session.flush = AsyncMock()
        queued: list[tuple[str, int]] = []

        async def fake_enqueue(_session, _player_id, *, kind, perfection_level, offer):
            queued.append((kind, perfection_level))
            return SimpleNamespace(id=len(queued), kind=kind, perfection_level=perfection_level)

        with (
            patch("waifu_bot.services.perfection._enqueue_pending", new=fake_enqueue),
            patch(
                "waifu_bot.services.waifu_hp.sync_waifu_stats",
                new_callable=AsyncMock,
            ),
        ):
            report = await reset_player_perfection_picks(
                session, player, claimed_skill_points=2
            )
        assert player.skill_points == 0
        assert player.perfection_bonus_totals == {}
        assert report["queued_bonus"] == 11
        assert report["queued_skill_point"] == 1
        assert report["skill_points_after"] == 0
        assert ("bonus", 11) in queued
        assert queued.count(("skill_point", 10)) == 1
        assert all(k != "skill_point" or lv == 10 for k, lv in queued)

    asyncio.run(_run())
