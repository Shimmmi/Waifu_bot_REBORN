"""Unit tests for daily GD schedule, stats, damage, and pie fallback."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from waifu_bot.game.constants import MediaType
from waifu_bot.game.msk_time import (
    gd_daily_window_active,
    gd_should_finalize_now,
    gd_should_start_now,
    msk_next_datetime,
)
from waifu_bot.services.gd_daily_stats import (
    apply_message_to_day_stats,
    build_player_summary_rows,
    calc_snapshot_message_damage,
    chat_message_share_pct,
    empty_day_stats,
    media_type_to_day_key,
    pick_mvp_and_least,
)
from waifu_bot.services.gd_chat_prefs import (
    filter_enroll_candidate_ids,
    participate_pref_enabled,
)
from waifu_bot.services.gd_daily_worker import (
    format_daily_finale_stats_html,
    format_daily_start_roster_html,
)
from waifu_bot.services.gd_pie_chart import render_pie_pillow

_MSK = ZoneInfo("Europe/Moscow")


class _Reg:
    def __init__(self, user_id: int, snap: dict, stats: dict | None = None):
        self.user_id = user_id
        self.waifu_snapshot = snap
        self.day_stats_json = stats


def test_msk_window_cross_midnight():
    # 05:00 MSK — inside day window
    now = datetime(2026, 8, 2, 5, 0, tzinfo=_MSK)
    assert gd_daily_window_active(now=now) is True
    # 03:00 MSK — still inside (before 04:00 end)
    now = datetime(2026, 8, 2, 3, 0, tzinfo=_MSK)
    assert gd_daily_window_active(now=now) is True
    # 04:15 MSK — quiet gap
    now = datetime(2026, 8, 2, 4, 15, tzinfo=_MSK)
    assert gd_daily_window_active(now=now) is False


def test_should_finalize_and_start_marks():
    assert gd_should_finalize_now(now=datetime(2026, 8, 2, 4, 5, tzinfo=_MSK)) is True
    assert gd_should_finalize_now(now=datetime(2026, 8, 2, 4, 35, tzinfo=_MSK)) is False
    assert gd_should_start_now(now=datetime(2026, 8, 2, 4, 29, tzinfo=_MSK)) is False
    assert gd_should_start_now(now=datetime(2026, 8, 2, 4, 30, tzinfo=_MSK)) is True


def test_next_end_after_0430_is_tomorrow_0400():
    start = datetime(2026, 8, 2, 4, 30, tzinfo=_MSK)
    ends = msk_next_datetime(4, 0, after=start)
    local = ends.astimezone(_MSK)
    assert local.hour == 4 and local.minute == 0
    assert local.date() == start.date().fromordinal(start.date().toordinal() + 1) or local.day == 3


def test_media_type_keys_and_stats_accumulate():
    assert media_type_to_day_key(MediaType.GIF) == "animation"
    assert media_type_to_day_key(MediaType.TEXT) == "text"
    s = empty_day_stats()
    s = apply_message_to_day_stats(s, msg_key="text", damage=12)
    s = apply_message_to_day_stats(s, msg_key="sticker", damage=5)
    assert s["msg_total"] == 2
    assert s["by_type"]["text"] == 1
    assert s["by_type"]["sticker"] == 1
    assert s["damage_total"] == 17


def test_damage_from_snapshot_without_solo():
    snap = {
        "strength": 20,
        "agility": 10,
        "intelligence": 10,
        "weapon_damage": 30,
        "attack_type": "melee",
    }
    dmg = calc_snapshot_message_damage(snap, MediaType.TEXT, message_length=40)
    assert dmg > 0
    dmg2 = calc_snapshot_message_damage(snap, MediaType.PHOTO, message_length=0)
    assert dmg2 > 0


def test_chat_share_and_mvp():
    assert chat_message_share_pct(25, 100) == 25.0
    assert chat_message_share_pct(1, 0) == 0.0
    regs = [
        _Reg(1, {"name": "A", "username": "aaa"}, {"msg_total": 10, "by_type": {"text": 10}, "damage_total": 100}),
        _Reg(2, {"name": "B", "username": "bbb"}, {"msg_total": 2, "by_type": {"text": 2}, "damage_total": 10}),
        _Reg(3, {"name": "C", "username": "ccc"}, {"msg_total": 0, "by_type": {}, "damage_total": 0}),
    ]
    rows = build_player_summary_rows(regs, chat_msg_total=20)
    mvp, least = pick_mvp_and_least(rows)
    assert mvp is not None and mvp["user_id"] == 1
    assert least is not None and least["user_id"] == 2


def test_start_and_finale_copy_readable():
    party = [
        {
            "user_id": 1,
            "username": "hero",
            "name": "Мира",
            "level": 12,
            "perfection_level": 3,
            "gear_score": 440,
        }
    ]
    roster = format_daily_start_roster_html(party)
    assert "@hero" not in roster
    assert "<b>Мира</b>" in roster
    assert ": 12," in roster
    assert "ур.шмота <b>440</b>" in roster
    assert "совершенствование" not in roster
    rows = build_player_summary_rows(
        [_Reg(1, party[0], {"msg_total": 5, "by_type": {"text": 5}, "damage_total": 99})],
        chat_msg_total=10,
    )
    html = format_daily_finale_stats_html(
        rows, chat_msg_total=10, dungeon_name="Тест", mvp=rows[0], least=rows[0]
    )
    assert "Итоги дневного похода" in html
    assert "50.0%" in html or "50%" in html
    assert "урон" in html.lower()
    assert "@" not in html
    assert "🏆 MVP: <b>Мира</b>" in html


def test_pie_pillow_fallback_produces_png():
    rows = [
        {"user_id": 1, "username": "a", "name": "A", "msg_total": 7},
        {"user_id": 2, "username": "b", "name": "B", "msg_total": 3},
    ]
    png = render_pie_pillow(rows, chat_msg_total=15, title="Тест диаграмма")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 1000


def test_pie_generate_falls_back_without_routerai(monkeypatch):
    import asyncio

    from waifu_bot.services import gd_pie_chart as mod

    monkeypatch.setattr(mod, "has_image_llm_configured", lambda: False)
    rows = [{"user_id": 1, "username": "a", "name": "A", "msg_total": 4}]
    png, src = asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        mod.generate_gd_daily_pie_png(rows, chat_msg_total=4)
    )
    assert src == "pillow"
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_pref_false_not_enrolled_default_true():
    assert participate_pref_enabled(None) is True
    enrolled = filter_enroll_candidate_ids([11, 22, 33], {22})
    assert 22 not in enrolled
    assert enrolled == [11, 33]
    # Finale rows come only from registrations — opted-out uid never appears.
    rows = build_player_summary_rows(
        [_Reg(11, {"name": "On"}, {"msg_total": 3, "by_type": {"text": 3}, "damage_total": 1})],
        chat_msg_total=3,
    )
    assert [r["user_id"] for r in rows] == [11]

