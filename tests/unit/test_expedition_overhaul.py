"""Unit tests: expedition v2 overhaul (power, heal, rewards)."""
from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from waifu_bot.db.models.waifu import WaifuRarity
from waifu_bot.game.expedition_overhaul import (
    DEPTH_TIERS,
    compute_hired_power,
    depth_tier_by_id,
    gate_log_entry,
    heal_duration_minutes,
    interpolate_heal_hp,
    pick_procedural_affixes,
    squad_power_total,
    tick_affix_count,
    validate_reward_type,
)
from waifu_bot.game.expedition_redesign import expedition_event_interval_minutes
from waifu_bot.services.expedition import ExpeditionService
from waifu_bot.services.hired_waifu_state import (
    effective_hired_hp,
    hired_expedition_eligible,
    start_heal_over_time,
)


def test_compute_hired_power_scales_with_level_and_rarity():
    common_l1 = compute_hired_power(1, int(WaifuRarity.COMMON))
    common_l10 = compute_hired_power(10, int(WaifuRarity.COMMON))
    rare_l1 = compute_hired_power(1, int(WaifuRarity.RARE))
    assert common_l10 > common_l1
    assert rare_l1 > common_l1


def test_squad_power_total_sums_units():
    u1 = MagicMock(power=80, level=5, rarity=1)
    u2 = MagicMock(power=120, level=8, rarity=3)
    assert squad_power_total([u1, u2]) == 200


def test_depth_tier_gate_thresholds():
    t1 = depth_tier_by_id(1)
    t5 = depth_tier_by_id(5)
    assert t1 is not None and t1.min_squad_power == 0
    assert t5 is not None and t5.min_squad_power == 300


def test_depth_tier_durations_doubled_events_unchanged():
    expected = {
        1: (60, 2),
        2: (90, 3),
        3: (120, 4),
        4: (180, 6),
        5: (240, 8),
    }
    for tier in DEPTH_TIERS:
        dur, events = expected[tier.tier]
        assert tier.duration_minutes == dur
        assert tier.events_count == events


def test_expedition_event_interval_minutes():
    assert expedition_event_interval_minutes(60, 2) == 30
    assert expedition_event_interval_minutes(30, 2) == 15
    assert expedition_event_interval_minutes(240, 8) == 30
    assert expedition_event_interval_minutes(30, 0) == 15


def test_validate_reward_type():
    assert validate_reward_type("gold") == "gold"
    assert validate_reward_type("MIXED") == "mixed"
    assert validate_reward_type("invalid") is None


def test_heal_duration_increases_with_missing_hp():
    short = heal_duration_minutes(90, 100)
    long = heal_duration_minutes(10, 100)
    assert long > short


def test_interpolate_heal_hp_linear():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    started = now
    complete = now + timedelta(minutes=100)
    mid = now + timedelta(minutes=50)
    hp_mid = interpolate_heal_hp(
        heal_start_hp=20,
        max_hp=100,
        heal_started_at=started,
        heal_complete_at=complete,
        now=mid,
    )
    assert 55 <= hp_mid <= 65


def test_gate_log_entry_text():
    entry = gate_log_entry(
        event_index=1,
        category="monsters",
        damage=5,
        covered=True,
        affix_names=["с пауками", "Туманная"],
    )
    assert "пройдено" in entry["text"]
    assert entry["damage"] == 5
    assert entry["affix_names"] == ["с пауками", "Туманная"]


def test_tick_affix_count_by_depth():
    assert tick_affix_count(1) == 1
    assert tick_affix_count(2) == 2
    assert tick_affix_count(3) == 2
    assert tick_affix_count(4) == 3
    assert tick_affix_count(5) == 3
    assert tick_affix_count(None) == 1


def test_pick_procedural_affixes_exclude_avoids_prev_when_possible():
    pool = [MagicMock(id=i, name=f"a{i}") for i in range(1, 8)]
    rng = random.Random(42)
    first = pick_procedural_affixes(pool, rng, count=2)
    first_ids = {int(a.id) for a in first}
    second = pick_procedural_affixes(pool, random.Random(43), count=2, exclude_ids=first_ids)
    second_ids = {int(a.id) for a in second}
    assert first_ids.isdisjoint(second_ids)


def test_pick_procedural_affixes_exclude_falls_back_when_pool_small():
    pool = [MagicMock(id=1), MagicMock(id=2)]
    picked = pick_procedural_affixes(pool, random.Random(1), count=2, exclude_ids=[1, 2])
    assert len(picked) == 2
    assert {int(a.id) for a in picked} == {1, 2}


def test_consecutive_tick_seeds_pick_different_affix_sets():
    """Different events_done seeds + exclude → different obstacle sets (large pool)."""
    pool = [MagicMock(id=i, name=f"affix-{i}") for i in range(1, 20)]
    active_id = 100
    picks = []
    exclude = []
    for events_done in range(3):
        rng = random.Random((active_id << 8) + events_done)
        chosen = pick_procedural_affixes(
            pool, rng, count=tick_affix_count(4), exclude_ids=exclude
        )
        ids = [int(a.id) for a in chosen]
        picks.append(tuple(sorted(ids)))
        exclude = ids
    assert len(set(picks)) >= 2


def test_hired_expedition_eligible_blocks_healing():
    now = datetime.now(tz=timezone.utc)
    w = MagicMock(
        expedition_id=None,
        max_hp=100,
        current_hp=100,
        heal_started_at=now,
        heal_complete_at=now + timedelta(hours=1),
        heal_start_hp=50,
        level=5,
        rarity=1,
    )
    ok, err = hired_expedition_eligible(w, now)
    assert not ok
    assert err == "waifu_healing"


def test_start_heal_over_time_sets_fields():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    w = MagicMock(max_hp=100, current_hp=40, heal_start_hp=None, heal_started_at=None, heal_complete_at=None)
    with patch("waifu_bot.services.hired_waifu_state.effective_hired_hp", return_value=(40, 100)):
        minutes = start_heal_over_time(w, now)
    assert minutes >= 5
    assert w.heal_started_at == now
    assert w.heal_complete_at is not None


@pytest.fixture
def service() -> ExpeditionService:
    return ExpeditionService()


def test_start_v2_delegates_when_reward_and_tier_set(service: ExpeditionService):
    async def _run():
        session = AsyncMock()
        expected = {"success": True, "active_id": 42}
        with patch(
            "waifu_bot.services.expedition_v2_start.start_expedition_v2",
            new_callable=AsyncMock,
            return_value=expected,
        ) as mock_v2:
            result = await service.start(session, 1, None, [10], 60, reward_type="gold", depth_tier=2)
        assert result == expected
        mock_v2.assert_awaited_once()

    asyncio.run(_run())


def test_start_v2_insufficient_power_from_delegate(service: ExpeditionService):
    async def _run():
        session = AsyncMock()
        err = {"error": "insufficient_power", "required": 150, "have": 50}
        with patch(
            "waifu_bot.services.expedition_v2_start.start_expedition_v2",
            new_callable=AsyncMock,
            return_value=err,
        ):
            result = await service.start(session, 1, None, [10], 60, reward_type="gold", depth_tier=3)
        assert result["error"] == "insufficient_power"

    asyncio.run(_run())
