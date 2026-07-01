"""Unit tests: GD v1 мульти-цикловый раунд — анти-спам склейка, реплей действий, MVP."""
from __future__ import annotations

from waifu_bot.services.gd_cycle_service import coalesce_round_action
from waifu_bot.services.gd_round_engine import _player_action_sequence
from waifu_bot.services.gd_v1_worker import _compute_round_mvp


def test_coalesce_text_series_merges_within_window() -> None:
    actions: list[dict] = []
    base = 1000.0
    for i in range(5):
        coalesce_round_action(
            actions,
            kind="text",
            now_ts=base + i * 0.1,
            text_len=3,
            window_seconds=8,
            max_actions=8,
        )
    assert len(actions) == 1
    assert actions[0]["count"] == 5
    assert actions[0]["len"] == 15


def test_coalesce_text_separate_when_outside_window() -> None:
    actions: list[dict] = []
    coalesce_round_action(actions, kind="text", now_ts=1000.0, text_len=3, window_seconds=8, max_actions=8)
    coalesce_round_action(actions, kind="text", now_ts=1025.0, text_len=4, window_seconds=8, max_actions=8)
    assert len(actions) == 2
    assert actions[0]["len"] == 3
    assert actions[1]["len"] == 4


def test_coalesce_media_distinct_types_separate() -> None:
    actions: list[dict] = []
    coalesce_round_action(actions, kind="media", media_kind="sticker", now_ts=1000.0, window_seconds=8, max_actions=8)
    coalesce_round_action(actions, kind="media", media_kind="photo", now_ts=1001.0, window_seconds=8, max_actions=8)
    assert len(actions) == 2


def test_coalesce_respects_max_actions_cap() -> None:
    actions: list[dict] = []
    base = 1000.0
    for i in range(12):
        coalesce_round_action(
            actions,
            kind="media",
            media_kind=("sticker" if i % 2 else "photo"),
            now_ts=base + i * 100,  # каждый раз вне окна -> новое действие, пока не достигнут cap
            window_seconds=8,
            max_actions=4,
        )
    assert len(actions) <= 4


def test_player_action_sequence_new_format() -> None:
    ub = {
        "actions": [
            {"kind": "text", "len": 10, "count": 2},
            {"kind": "media", "media_kind": "sticker", "count": 1},
        ]
    }
    seq = _player_action_sequence(ub)
    assert len(seq) == 2
    assert seq[0] == {"kind": "text", "len": 10, "count": 2}
    assert seq[1]["kind"] == "media" and seq[1]["media_kind"] == "sticker"


def test_player_action_sequence_legacy_fallback() -> None:
    ub = {"text_len": 40, "media": ["photo", "sticker"]}
    seq = _player_action_sequence(ub)
    assert seq[0]["kind"] == "text" and seq[0]["len"] == 40
    media = [a["media_kind"] for a in seq if a["kind"] == "media"]
    assert media == ["photo", "sticker"]


def test_player_action_sequence_empty_for_silent() -> None:
    assert _player_action_sequence({}) == []
    assert _player_action_sequence({"text_len": 0, "media": []}) == []


def test_compute_round_mvp_prefers_higher_activity() -> None:
    state = {
        "party": [{"user_id": 1, "name": "Аня"}, {"user_id": 2, "name": "Бэль"}],
        "activity_totals": {"1": 10.0, "2": 100.0},
    }
    assert _compute_round_mvp(state) == (2, "Бэль")


def test_compute_round_mvp_contribution_fallback() -> None:
    state = {
        "party": [{"user_id": 1, "name": "Аня"}, {"user_id": 2, "name": "Бэль"}],
        "contribution": {
            "1": {"text": 100, "skill": 0, "heal": 0, "rounds": 1},
            "2": {"text": 5, "skill": 0, "heal": 0, "rounds": 1},
        },
    }
    mvp = _compute_round_mvp(state)
    assert mvp is not None and mvp[0] == 1


def test_compute_round_mvp_none_when_empty() -> None:
    assert _compute_round_mvp({"party": []}) is None
