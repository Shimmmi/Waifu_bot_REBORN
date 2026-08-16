"""Unit tests for Steam PC hits batch (delegates to activity claim)."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from waifu_bot.api import pc_client_routes
from waifu_bot.api.pc_client_routes import PcHitBatchIn, submit_pc_hit_batch
from waifu_bot.game.economy import SOURCE_STEAM_CLICKS


@pytest.mark.asyncio
async def test_batch_delegates_to_activity_claim(monkeypatch):
    monkeypatch.setattr(
        pc_client_routes, "ensure_activity_starter_gear", AsyncMock(return_value=None)
    )
    mock_claim = AsyncMock(
        return_value={
            "accepted_units": 3,
            "buffer_left": 0,
            "hits_applied": 1,
            "rejected_reason": None,
            "results": [{"spend": 3, "damage_done": 5}],
        }
    )
    monkeypatch.setattr(pc_client_routes, "claim_activity_input", mock_claim)

    out = await submit_pc_hit_batch(
        PcHitBatchIn(hit_count=3), player_id=123, session=AsyncMock()
    )

    assert out.requested == 3
    assert out.applied == 1
    assert out.accepted_units == 3
    assert mock_claim.await_count == 1
    kwargs = mock_claim.await_args.kwargs
    assert kwargs["source"] == SOURCE_STEAM_CLICKS
    assert kwargs["units"] == 3


@pytest.mark.asyncio
async def test_batch_propagates_no_active_battle(monkeypatch):
    monkeypatch.setattr(
        pc_client_routes, "ensure_activity_starter_gear", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        pc_client_routes,
        "claim_activity_input",
        AsyncMock(
            return_value={
                "accepted_units": 5,
                "buffer_left": 5,
                "hits_applied": 0,
                "rejected_reason": "no_active_battle",
                "results": [],
            }
        ),
    )

    out = await submit_pc_hit_batch(
        PcHitBatchIn(hit_count=5), player_id=123, session=AsyncMock()
    )

    assert out.applied == 0
    assert out.rejected_reason == "no_active_battle"
