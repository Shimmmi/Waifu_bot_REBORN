"""Unit tests for guild quest service."""
from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from waifu_bot.services.guild_quest_service import (
    _daily_period_key,
    _progress_pct,
    _quest_card_dto,
    _tier_statuses,
    record_metric,
    vote_weekly_quest,
)


def test_progress_pct_mid_tier():
    assert _progress_pct(500, 100, 1000) == pytest.approx(44.4, abs=0.2)


def test_tier_statuses_marks_done_and_active():
    tiers = [
        SimpleNamespace(id=1, tier=1, target_value=100, reward_xp=50, name_suffix=" I"),
        SimpleNamespace(id=2, tier=2, target_value=1000, reward_xp=200, name_suffix=" II"),
    ]
    out = _tier_statuses(tiers, current_val=500, active_tier_id=2)
    assert out[0]["status"] == "done"
    assert out[1]["status"] == "active"


def test_quest_card_dto_milestone_name():
    quest = SimpleNamespace(
        id=1,
        tier_id=2,
        current_val=500,
        target_value=None,
        reward_xp=None,
        status="active",
        completed_at=None,
        expires_at=None,
    )
    template = SimpleNamespace(
        id=10,
        name="Стикер-марафон",
        description="desc",
        category="chat",
        type="milestone",
        metric="stickers_sent",
        target_value=None,
        reward_xp=None,
    )
    tiers = [
        SimpleNamespace(id=1, tier=1, target_value=100, reward_xp=50, name_suffix=" I"),
        SimpleNamespace(id=2, tier=2, target_value=1000, reward_xp=200, name_suffix=" II"),
    ]
    card = _quest_card_dto(quest, template, tiers, [], 0)
    assert card["name"] == "Стикер-марафон II"
    assert card["target"] == 1000
    assert card["current"] == 500


def test_record_metric_no_guild_skips():
    async def _run():
        session = AsyncMock()
        with patch(
            "waifu_bot.services.guild_quest_service.get_player_guild_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await record_metric(session, 1, "stickers_sent", 1)
        session.execute.assert_not_called()

    asyncio.run(_run())


def test_vote_weekly_quest_officer_only():
    async def _run():
        session = AsyncMock()
        mem = SimpleNamespace(guild_id=5, is_leader=False, is_officer=False)
        session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mem))
        )
        result = await vote_weekly_quest(session, 99, 1)
        assert result == {"error": "officer_only"}

    asyncio.run(_run())


def test_daily_period_key_format():
    with patch("waifu_bot.services.guild_quest_service.msk_today", return_value=date(2026, 6, 5)):
        assert _daily_period_key() == "daily:2026-06-05"
