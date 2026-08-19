"""Unit tests for hidden milestone skills (progress category)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from waifu_bot.db.models.hidden_skill import HiddenSkillDefinition
from waifu_bot.game.hidden_effect_labels import format_hidden_effect_value
from waifu_bot.services.hidden_milestones import (
    APEX_THRESHOLDS,
    MILESTONE_SKILL_IDS,
    PARAGON_THRESHOLDS,
    compute_milestone_counters,
    sync_milestone_skills,
)
from waifu_bot.services.hidden_skills import _apply_level_for_skill, _level_from_counter, effects_for_level


def test_milestone_catalog_size_and_ids() -> None:
    assert len(MILESTONE_SKILL_IDS) == 13
    assert len(set(MILESTONE_SKILL_IDS)) == 13
    assert "legend" not in MILESTONE_SKILL_IDS
    for sid in MILESTONE_SKILL_IDS:
        assert 1 <= len(sid) <= 32


def test_apex_thresholds_level_60_is_max() -> None:
    th = APEX_THRESHOLDS
    assert _level_from_counter(th, 9) == 0
    assert _level_from_counter(th, 10) == 1
    assert _level_from_counter(th, 20) == 2
    assert _level_from_counter(th, 30) == 3
    assert _level_from_counter(th, 40) == 4
    assert _level_from_counter(th, 50) == 4
    assert _level_from_counter(th, 60) == 5


def test_paragon_every_ten_levels() -> None:
    th = PARAGON_THRESHOLDS
    assert _level_from_counter(th, 0) == 0
    assert _level_from_counter(th, 9) == 0
    assert _level_from_counter(th, 10) == 1
    assert _level_from_counter(th, 25) == 2
    assert _level_from_counter(th, 40) == 4
    assert _level_from_counter(th, 50) == 5


def test_apex_l5_all_stats_is_modest() -> None:
    defn = SimpleNamespace(
        effect_types=["all_stats_pct"],
        effect_values=[0.5, 1, 1.5, 2, 3],
    )
    assert effects_for_level(defn, 1)["all_stats_pct"] == pytest.approx(0.5)
    assert effects_for_level(defn, 3)["all_stats_pct"] == pytest.approx(1.5)
    assert effects_for_level(defn, 5)["all_stats_pct"] == pytest.approx(3)
    assert format_hidden_effect_value("all_stats_pct", 0.5) == "+0.5 п.п."
    assert format_hidden_effect_value("all_stats_pct", 1.5) == "+1.5 п.п."
    assert format_hidden_effect_value("all_stats_pct", 3) == "+3 п.п."


def test_counts_toward_legend_defaults_true() -> None:
    col = HiddenSkillDefinition.__table__.c.counts_toward_legend
    assert col is not None
    assert col.default.arg is True


def test_compute_uses_precomputed_without_session() -> None:
    out = asyncio.run(
        compute_milestone_counters(
            None,  # type: ignore[arg-type]
            42,
            ["apex", "paragon"],
            precomputed={"apex": 60, "paragon": 25},
        )
    )
    assert out == {"apex": 60, "paragon": 25}
    assert _level_from_counter(APEX_THRESHOLDS, out["apex"]) == 5
    assert _level_from_counter(PARAGON_THRESHOLDS, out["paragon"]) == 2


def test_sync_milestone_skills_silent_max(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    async def fake_set(
        session, player_id, skill_id, counter, *, silent=False, mode="replace", refresh_legend=True
    ):
        calls.append(
            {
                "player_id": player_id,
                "skill_id": skill_id,
                "counter": counter,
                "silent": silent,
                "mode": mode,
            }
        )

    monkeypatch.setattr("waifu_bot.services.hidden_milestones.set_skill_counter", fake_set)
    asyncio.run(
        sync_milestone_skills(
            AsyncMock(),
            7,
            ["apex", "paragon"],
            precomputed={"apex": 60, "paragon": 25},
            silent=True,
        )
    )
    by_id = {c["skill_id"]: c for c in calls}
    assert by_id["apex"]["counter"] == 60
    assert by_id["paragon"]["counter"] == 25
    assert all(c["silent"] is True and c["mode"] == "max" for c in calls)


def test_apply_level_silent_skips_group_announce(monkeypatch: pytest.MonkeyPatch) -> None:
    announced: list[int] = []

    async def fake_announce(*_a, **_k):
        announced.append(1)

    monkeypatch.setattr(
        "waifu_bot.services.hidden_skills._maybe_announce_group_skill_unlock",
        fake_announce,
    )
    defn = SimpleNamespace(
        thresholds=APEX_THRESHOLDS, name="Предел формы", announce_in_group=True
    )
    row = SimpleNamespace(counter=60, level=0, unlocked_at=None, last_level_up=None)
    session = AsyncMock()
    session.get = AsyncMock(return_value=defn)
    session.execute = AsyncMock(
        return_value=SimpleNamespace(scalar_one_or_none=lambda: row)
    )
    asyncio.run(_apply_level_for_skill(session, 1, "apex", silent=True))
    assert row.level == 5
    assert announced == []


def test_sync_ignores_unknown_skill_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def fake_set(
        session, player_id, skill_id, counter, *, silent=False, mode="replace", refresh_legend=True
    ):
        calls.append(skill_id)

    monkeypatch.setattr("waifu_bot.services.hidden_milestones.set_skill_counter", fake_set)
    asyncio.run(
        sync_milestone_skills(
            AsyncMock(),
            1,
            ["apex", "not_a_skill", "legend"],
            precomputed={"apex": 10, "legend": 5},
            silent=True,
        )
    )
    assert calls == ["apex"]
