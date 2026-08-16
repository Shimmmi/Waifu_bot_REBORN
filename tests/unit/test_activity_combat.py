"""Unit tests for activity input claim (steps/clicks = TEXT chars)."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from waifu_bot.game.constants import MediaType
from waifu_bot.game.economy import ECONOMY_ACTIVITY, SOURCE_MOBILE_STEPS, SOURCE_STEAM_CLICKS
from waifu_bot.services import activity_combat


def _cfg(**overrides):
    base = {
        "activity.chunk_mode": "fill_cap",
        "activity.max_hits_per_claim": "5",
        "activity.max_units_per_claim": "2000",
        "activity.max_steps_per_day": "20000",
        "activity.max_clicks_per_day": "50000",
        "activity.max_step_rate_per_sec": "100",
        "activity.length_cap": "200",
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_claim_buffers_below_min_chars(monkeypatch):
    state = MagicMock()
    state.buffer_units = 0
    state.units_accepted_today = 0
    state.hits_applied_today = 0
    state.day_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    state.last_claim_at = None
    state.last_counter = None

    session = AsyncMock()
    session.get = AsyncMock(return_value=state)
    session.commit = AsyncMock()

    monkeypatch.setattr(activity_combat, "get_game_config_map", AsyncMock(return_value=_cfg()))
    monkeypatch.setattr(
        activity_combat, "fetch_equipped_inventory_items", AsyncMock(return_value=[])
    )
    # unarmed → min_chars 1 via resolve; patch to 3
    monkeypatch.setattr(activity_combat, "resolve_main_weapon_attack_speed", lambda _eq: 3)

    combat = MagicMock()
    combat.process_message_damage = AsyncMock()

    out = await activity_combat.claim_activity_input(
        session,
        42,
        source=SOURCE_MOBILE_STEPS,
        units=2,
        combat_service=combat,
    )

    assert out["accepted_units"] == 2
    assert out["buffer_left"] == 2
    assert out["hits_applied"] == 0
    assert out["units_to_next_hit"] == 1
    combat.process_message_damage.assert_not_awaited()


@pytest.mark.asyncio
async def test_claim_applies_text_hit_when_buffer_enough(monkeypatch):
    state = MagicMock()
    state.buffer_units = 0
    state.units_accepted_today = 0
    state.hits_applied_today = 0
    state.day_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    state.last_claim_at = None
    state.last_counter = None

    session = AsyncMock()
    session.get = AsyncMock(return_value=state)
    session.commit = AsyncMock()

    monkeypatch.setattr(activity_combat, "get_game_config_map", AsyncMock(return_value=_cfg()))
    monkeypatch.setattr(
        activity_combat, "fetch_equipped_inventory_items", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(activity_combat, "resolve_main_weapon_attack_speed", lambda _eq: 3)

    combat = MagicMock()
    combat.process_message_damage = AsyncMock(return_value={"damage_done": 10})

    out = await activity_combat.claim_activity_input(
        session,
        42,
        source=SOURCE_STEAM_CLICKS,
        units=3,
        combat_service=combat,
    )

    assert out["hits_applied"] == 1
    assert out["buffer_left"] == 0
    assert out["economy"] == ECONOMY_ACTIVITY
    call = combat.process_message_damage.await_args
    assert call.kwargs.get("economy") == ECONOMY_ACTIVITY
    assert call.kwargs.get("message_length") == 3
    assert call.args[2] == MediaType.TEXT


@pytest.mark.asyncio
async def test_reboot_counter_does_not_credit_negative(monkeypatch):
    state = MagicMock()
    state.buffer_units = 0
    state.units_accepted_today = 0
    state.hits_applied_today = 0
    state.day_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    state.last_claim_at = None
    state.last_counter = 5000

    session = AsyncMock()
    session.get = AsyncMock(return_value=state)
    session.commit = AsyncMock()

    monkeypatch.setattr(activity_combat, "get_game_config_map", AsyncMock(return_value=_cfg()))
    monkeypatch.setattr(
        activity_combat, "fetch_equipped_inventory_items", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(activity_combat, "resolve_main_weapon_attack_speed", lambda _eq: 3)

    out = await activity_combat.claim_activity_input(
        session,
        42,
        source=SOURCE_MOBILE_STEPS,
        units=100,
        client_counter_total=10,  # reboot
        combat_service=MagicMock(process_message_damage=AsyncMock()),
    )

    assert out["accepted_units"] == 0
    assert state.last_counter == 10


@pytest.mark.asyncio
async def test_invalid_source_rejected(monkeypatch):
    session = AsyncMock()
    out = await activity_combat.claim_activity_input(
        session, 1, source="taps", units=10
    )
    assert out["rejected_reason"] == "invalid_source"
    assert out["hits_applied"] == 0
