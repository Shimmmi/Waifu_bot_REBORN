"""Unit tests for daily GD participate prefs, enroll filter, and chat list payload."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from waifu_bot.services.gd_chat_prefs import (
    build_gd_chat_row,
    filter_enroll_candidate_ids,
    load_gd_opt_out_player_ids,
    participate_pref_enabled,
    player_share_pct,
    set_gd_participate,
    sort_gd_chat_rows,
)
from waifu_bot.services.gd_daily_stats import build_player_summary_rows


class _Reg:
    def __init__(self, user_id: int, snap: dict, stats: dict | None = None):
        self.user_id = user_id
        self.waifu_snapshot = snap
        self.day_stats_json = stats


def test_participate_pref_default_true():
    assert participate_pref_enabled(None) is True
    assert participate_pref_enabled(SimpleNamespace(participate=True)) is True
    assert participate_pref_enabled(SimpleNamespace(participate=False)) is False


def test_filter_enroll_skips_opted_out():
    assert filter_enroll_candidate_ids([1, 2, 3], {2}) == [1, 3]
    assert filter_enroll_candidate_ids([10], set()) == [10]
    assert filter_enroll_candidate_ids([7], {7}) == []


def test_player_share_pct_one_decimal():
    assert player_share_pct(1, 3) == 33.3
    assert player_share_pct(0, 0) == 0.0
    assert player_share_pct(5, 5) == 100.0


def test_sort_gd_chat_rows_roster_then_title():
    rows = [
        {"chat_id": -2, "title": "Beta", "in_today_roster": False},
        {"chat_id": -3, "title": "Alpha", "in_today_roster": True},
        {"chat_id": -1, "title": "Gamma", "in_today_roster": True},
    ]
    ordered = sort_gd_chat_rows(rows)
    assert [r["title"] for r in ordered] == ["Alpha", "Gamma", "Beta"]


def test_build_row_without_cycle():
    row = build_gd_chat_row(
        chat_id=-100,
        title="",
        participate=True,
        cycle=None,
        registration=None,
        chat_msg_total=99,
    )
    assert row["title"] == "Чат -100"
    assert row["participate"] is True
    assert row["in_today_roster"] is False
    assert row["cycle_id"] is None
    assert row["player_msg_total"] == 0
    assert row["chat_msg_total"] == 0
    assert row["player_share_pct"] == 0.0


def test_build_row_in_roster_share():
    cycle = SimpleNamespace(
        id=9,
        status="active",
        game_date=None,
        ends_at=datetime(2026, 8, 20, 1, 0, tzinfo=timezone.utc),
        battle_state_json={"mode": "daily"},
    )
    reg = _Reg(1, {"name": "A"}, {"msg_total": 25, "damage_total": 10})
    row = build_gd_chat_row(
        chat_id=-50,
        title=" Гильдия ",
        participate=False,
        cycle=cycle,
        registration=reg,
        chat_msg_total=100,
    )
    assert row["title"] == "Гильдия"
    assert row["participate"] is False
    assert row["in_today_roster"] is True
    assert row["cycle_id"] == 9
    assert row["player_msg_total"] == 25
    assert row["chat_msg_total"] == 100
    assert row["player_share_pct"] == 25.0
    assert row["ends_at"]


def test_opted_out_not_in_finale_summary_rows():
    enrolled = _Reg(1, {"name": "In"}, {"msg_total": 4, "by_type": {"text": 4}, "damage_total": 8})
    rows = build_player_summary_rows([enrolled], chat_msg_total=10)
    assert [r["user_id"] for r in rows] == [1]
    assert 99 not in {r["user_id"] for r in rows}


@pytest.mark.asyncio
async def test_load_opt_out_ids_from_query():
    class _Result:
        def all(self):
            return [(42,)]

    session = AsyncMock()
    session.execute = AsyncMock(return_value=_Result())
    ids = await load_gd_opt_out_player_ids(session, -100, [1, 42, 7])
    assert ids == {42}
    empty = await load_gd_opt_out_player_ids(session, -100, [])
    assert empty == set()
    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_set_participate_forbidden():
    session = AsyncMock()
    with patch(
        "waifu_bot.services.gd_chat_prefs.player_has_active_bot_chat",
        new=AsyncMock(return_value=False),
    ):
        result = await set_gd_participate(session, 1, -100, False)
    assert result["error"] == "forbidden"
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_participate_upsert_idempotent():
    session = AsyncMock()
    session.execute = AsyncMock()
    with patch(
        "waifu_bot.services.gd_chat_prefs.player_has_active_bot_chat",
        new=AsyncMock(return_value=True),
    ):
        first = await set_gd_participate(session, 1, -100, False)
        second = await set_gd_participate(session, 1, -100, False)
    assert first == second
    assert first["ok"] is True
    assert first["participate"] is False
    assert first["chat_id"] == -100
    assert session.execute.await_count == 2
