"""Unit tests for the Steam desktop client's batched-hits endpoint."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from waifu_bot.api import pc_client_routes
from waifu_bot.api.pc_client_routes import MAX_HITS_PER_REQUEST, PcHitBatchIn, submit_pc_hit_batch


@pytest.mark.asyncio
async def test_batch_applies_all_hits_when_under_cap(monkeypatch):
    mock_hit = AsyncMock(return_value={"damage_done": 5})
    monkeypatch.setattr(pc_client_routes.combat_service, "process_message_damage", mock_hit)

    out = await submit_pc_hit_batch(
        PcHitBatchIn(hit_count=3), player_id=123, session=AsyncMock()
    )

    assert out.requested == 3
    assert out.applied == 3
    assert out.rejected_reason is None
    assert mock_hit.await_count == 3
    for call in mock_hit.await_args_list:
        assert call.kwargs.get("skip_spam_check") is True


@pytest.mark.asyncio
async def test_batch_skips_spam_gate_for_pc_hits(monkeypatch):
    mock_hit = AsyncMock(
        side_effect=[
            {"damage_done": 5},
            {"damage_done": 5},
            {"damage_done": 5},
        ]
    )
    monkeypatch.setattr(pc_client_routes.combat_service, "process_message_damage", mock_hit)

    out = await submit_pc_hit_batch(
        PcHitBatchIn(hit_count=3), player_id=123, session=AsyncMock()
    )

    assert out.applied == 3
    assert out.rejected_reason is None
    assert mock_hit.await_count == 3
    for call in mock_hit.await_args_list:
        assert call.kwargs.get("skip_spam_check") is True


@pytest.mark.asyncio
async def test_batch_stops_early_on_no_active_battle(monkeypatch):
    mock_hit = AsyncMock(return_value={"error": "no_active_battle"})
    monkeypatch.setattr(pc_client_routes.combat_service, "process_message_damage", mock_hit)

    out = await submit_pc_hit_batch(
        PcHitBatchIn(hit_count=5), player_id=123, session=AsyncMock()
    )

    assert out.applied == 0
    assert out.rejected_reason == "no_active_battle"
    assert mock_hit.await_count == 1
    assert mock_hit.await_args.kwargs.get("skip_spam_check") is True


@pytest.mark.asyncio
async def test_batch_never_exceeds_hard_cap_per_request(monkeypatch):
    mock_hit = AsyncMock(return_value={"damage_done": 1})
    monkeypatch.setattr(pc_client_routes.combat_service, "process_message_damage", mock_hit)

    out = await submit_pc_hit_batch(
        PcHitBatchIn(hit_count=1000), player_id=123, session=AsyncMock()
    )

    assert mock_hit.await_count == MAX_HITS_PER_REQUEST
    assert out.applied == MAX_HITS_PER_REQUEST
    assert out.rejected_reason == "batch_capped"
