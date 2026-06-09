"""Unit tests for chat rewards daily auto-claim helpers."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from waifu_bot.services.chat_rewards import ClaimResult, auto_claim_all_wallets


def test_auto_claim_all_wallets_claims_non_empty(monkeypatch):
    session = AsyncMock()
    redis = AsyncMock()
    player_ids = [10, 20]

    session.execute = AsyncMock(
        return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=player_ids))))
    )

    flush_mock = AsyncMock()
    claim_results = [
        ClaimResult(ok=True, gold=5, exp=0, chests=0),
        ClaimResult(ok=True, gold=0, exp=0, chests=0),
    ]
    claim_mock = AsyncMock(side_effect=claim_results)
    monkeypatch.setattr("waifu_bot.services.chat_rewards.flush_buffer_to_db", flush_mock)
    monkeypatch.setattr("waifu_bot.services.chat_rewards.claim_wallet", claim_mock)

    out = asyncio.run(auto_claim_all_wallets(session, redis))

    flush_mock.assert_awaited_once_with(session, redis)
    assert claim_mock.await_count == 2
    assert out == [(10, claim_results[0])]


def test_auto_claim_all_wallets_skips_empty_results(monkeypatch):
    session = AsyncMock()
    redis = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[99]))))
    )
    monkeypatch.setattr("waifu_bot.services.chat_rewards.flush_buffer_to_db", AsyncMock())
    monkeypatch.setattr(
        "waifu_bot.services.chat_rewards.claim_wallet",
        AsyncMock(return_value=ClaimResult(ok=True, gold=0, exp=0, chests=0)),
    )

    out = asyncio.run(auto_claim_all_wallets(session, redis))
    assert out == []
