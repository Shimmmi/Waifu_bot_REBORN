"""Finale polish: waifu names, compact HTML, DM aggregate, podium pillow, send retries."""
from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

from waifu_bot.services.gd_daily_stats import (
    build_player_summary_rows,
    format_top_words_line_ru,
    format_waifu_html,
    should_omit_words_line,
)
from waifu_bot.services.gd_daily_word_ai import merge_word_stats_into_rows
from waifu_bot.services.gd_daily_worker import (
    _chunk_plain_text,
    _is_permanent_telegram_dm_error,
    flush_daily_reward_dms,
    format_aggregated_reward_dm,
    format_daily_finale_stats_html,
    format_daily_start_roster_html,
)
from waifu_bot.services.gd_podium_art import (
    count_active_players,
    podium_caption_from_rows,
    render_podium_pillow,
    render_race_leaderboard_pillow,
    send_photo_with_retries,
    should_generate_podium,
    top_active_rows,
    _face_crop_from_avatar,
)


class _Reg:
    def __init__(self, user_id: int, snap: dict, stats: dict | None = None):
        self.user_id = user_id
        self.waifu_snapshot = snap
        self.day_stats_json = stats


def test_format_waifu_html_escapes_and_no_at():
    assert format_waifu_html("Мира") == "<b>Мира</b>"
    assert "&lt;" in format_waifu_html("<script>")
    assert format_waifu_html("@hero") == "<b>hero</b>"
    assert "@" not in format_waifu_html("@hero")


def test_start_roster_waifu_only():
    party = [
        {
            "user_id": 1,
            "username": "hero",
            "name": "Мира",
            "level": 12,
            "perfection_level": 0,
            "gear_score": 440,
        }
    ]
    roster = format_daily_start_roster_html(party)
    assert "@hero" not in roster
    assert "<b>Мира</b>" in roster
    assert "ур.шмота <b>440</b>" in roster


def test_finale_omits_words_and_silent_sublines():
    regs = [
        _Reg(
            1,
            {"name": "A", "username": "aaa"},
            {"msg_total": 0, "by_type": {}, "damage_total": 0, "text_chars": 0},
        ),
        _Reg(
            2,
            {"name": "B&B", "username": "bbb"},
            {
                "msg_total": 8,
                "by_type": {"text": 5, "sticker": 3},
                "damage_total": 40,
                "text_chars": 100,
            },
        ),
        _Reg(
            3,
            {"name": "C", "username": "ccc"},
            {"msg_total": 2, "by_type": {"text": 2}, "damage_total": 5, "text_chars": 10},
        ),
    ]
    rows = build_player_summary_rows(regs, chat_msg_total=12)
    merge_word_stats_into_rows(
        rows,
        {
            2: {
                "top_words": [{"word": "кот", "count": 5}],
                "no_word_repeated": False,
                "words_unavailable": False,
            },
            3: {"top_words": [], "no_word_repeated": True, "words_unavailable": False},
        },
    )
    html = format_daily_finale_stats_html(
        rows, chat_msg_total=12, dungeon_name="Тест", mvp=rows[1], least=rows[2]
    )
    assert "@" not in html
    assert "tg://user" not in html
    assert "<b>B&amp;B</b>" in html  # html.escape
    assert "кот (5)" in html
    assert "нет повторов слов" not in html
    assert "Без сообщений" not in html
    # silent player: no media/words sublines after their zero line
    # Find A's block — should not contain └ after their header before next player
    assert "медиа:" in html  # active players still have media
    silent_idx = html.index("<b>A</b>")
    # Between A and next ranking number there should be no └ 
    # A is last by activity (0 msgs) — after A only footer
    after_a = html[silent_idx:]
    # First line for A should not include └ медиа
    first_line = after_a.split("\n")[0]
    assert "└" not in first_line
    assert "🏆 MVP: <b>" in html
    assert "(" not in html.split("MVP:")[1].split("\n")[0] or "MVP: <b>" in html


def test_should_omit_words_line():
    assert should_omit_words_line({"msg_total": 0}) is True
    assert should_omit_words_line({"msg_total": 2, "no_word_repeated": True}) is True
    assert should_omit_words_line({"msg_total": 2, "words_unavailable": True}) is True
    assert (
        should_omit_words_line(
            {"msg_total": 2, "top_words": [{"word": "a", "count": 3}], "no_word_repeated": False}
        )
        is False
    )
    assert format_top_words_line_ru({"msg_total": 2, "no_word_repeated": True}) is None


def test_aggregated_dm_sums_two_chats():
    parts = [
        {
            "dungeon_name": "Лес",
            "rank": 1,
            "party_size": 3,
            "msg_total": 10,
            "counted_msgs": 10,
            "damage_total": 100,
            "exp": 50,
            "gold": 80,
            "items": [{"name": "Меч", "level": 5}],
        },
        {
            "dungeon_name": "Пещера",
            "rank": 2,
            "party_size": 2,
            "msg_total": 4,
            "counted_msgs": 4,
            "damage_total": 20,
            "exp": 20,
            "gold": 30,
            "items": [],
        },
    ]
    text = format_aggregated_reward_dm(game_date=date(2026, 8, 2), parts=parts)
    assert "Итого: 70 опыта, 110 золота" in text
    assert "Лес" in text and "Пещера" in text
    assert text.count("⚔️") == 1
    chunks = _chunk_plain_text(text, soft_limit=80)
    assert len(chunks) >= 1


def test_should_generate_podium_activity_gate():
    silent = [
        {"user_id": 1, "name": "А", "msg_total": 0},
        {"user_id": 2, "name": "Б", "msg_total": 0},
    ]
    assert count_active_players(silent) == 0
    assert should_generate_podium(silent) is False
    assert should_generate_podium([]) is False

    one = [{"user_id": 1, "name": "А", "msg_total": 4}]
    assert count_active_players(one) == 1
    assert should_generate_podium(one) is True

    two = [
        {"user_id": 1, "name": "А", "msg_total": 4},
        {"user_id": 2, "name": "Б", "msg_total": 3},
        {"user_id": 3, "name": "Молчун", "msg_total": 0},
    ]
    assert count_active_players(two) == 2
    assert should_generate_podium(two) is True


def test_race_leaderboard_pillow_and_face_crop():
    from io import BytesIO

    from PIL import Image

    # Fake tall avatar for face crop
    fake = Image.new("RGB", (200, 400), (180, 120, 140))
    buf = BytesIO()
    fake.save(buf, format="PNG")
    raw = buf.getvalue()
    face = _face_crop_from_avatar(raw, size=72)
    assert face.size == (72, 72)
    empty = _face_crop_from_avatar(None, size=64)
    assert empty.size == (64, 64)

    rows = [
        {
            "user_id": 1,
            "name": "Альфа",
            "msg_total": 9,
            "text_chars": 120,
            "chat_share_pct": 50.0,
            "by_type": {"text": 7, "sticker": 2},
        },
        {
            "user_id": 2,
            "name": "Бета",
            "msg_total": 5,
            "text_chars": 40,
            "chat_share_pct": 30.0,
            "by_type": {"text": 3, "photo": 2},
        },
        {
            "user_id": 3,
            "name": "Гамма",
            "msg_total": 3,
            "text_chars": 10,
            "chat_share_pct": 20.0,
            "by_type": {"text": 3},
        },
        {"user_id": 4, "name": "Тишь", "msg_total": 0, "text_chars": 0, "chat_share_pct": 0.0},
    ]
    webp = render_race_leaderboard_pillow(
        rows,
        avatars={1: raw, 2: None},
        title="Тест забега",
    )
    assert webp[:4] == b"RIFF" and webp[8:12] == b"WEBP"
    cap = podium_caption_from_rows(rows)
    assert "@" not in cap
    assert "Альфа" in cap and "Бета" in cap
    assert "Тишь" not in cap

    # empty active → ValueError from renderer
    try:
        render_race_leaderboard_pillow(
            [{"user_id": 9, "name": "X", "msg_total": 0}],
            avatars={},
            title="Пусто",
        )
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_podium_pillow_layouts_and_caption():
    rows = [
        {"user_id": 1, "name": "Альфа", "msg_total": 9},
        {"user_id": 2, "name": "Бета", "msg_total": 5},
        {"user_id": 3, "name": "Гамма", "msg_total": 3},
        {"user_id": 4, "name": "Тишь", "msg_total": 0},
    ]
    top = top_active_rows(rows, limit=3)
    assert len(top) == 3
    webp3 = render_podium_pillow(top, avatars={}, title="Тест")
    assert webp3[:4] == b"RIFF" and webp3[8:12] == b"WEBP"
    webp1 = render_podium_pillow(top[:1], avatars={1: None}, title="Один")
    assert webp1[:4] == b"RIFF" and webp1[8:12] == b"WEBP"


def test_send_photo_retries_without_regen():
    calls = {"n": 0}

    class _Bot:
        async def send_photo(self, **kwargs: Any) -> None:
            calls["n"] += 1
            if calls["n"] < 3:
                raise ConnectionError("reset")
            return None

    # Minimal valid-looking WEBP header + padding for compress path
    tiny = b"RIFF" + (30).to_bytes(4, "little") + b"WEBP" + b"\x00" * 30
    ok = asyncio.run(
        send_photo_with_retries(
            _Bot(),
            chat_id=-100,
            png=tiny,
            filename="t.webp",
            caption="cap",
            max_attempts=3,
        )
    )
    assert ok is True
    assert calls["n"] == 3


def test_is_permanent_telegram_dm_error():
    from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
    from aiogram.methods import SendMessage

    method = SendMessage(chat_id=1, text="x")
    assert _is_permanent_telegram_dm_error(
        TelegramForbiddenError(method=method, message="Forbidden: bot was blocked by the user")
    )
    assert _is_permanent_telegram_dm_error(
        TelegramBadRequest(method=method, message="Bad Request: chat not found")
    )
    assert _is_permanent_telegram_dm_error(RuntimeError("user is deactivated")) is True
    assert _is_permanent_telegram_dm_error(ConnectionError("reset by peer")) is False


def test_flush_settles_forbidden_and_prefs_off(monkeypatch):
    from aiogram.exceptions import TelegramForbiddenError
    from aiogram.methods import SendMessage
    from waifu_bot.services import gd_daily_worker as worker

    class _Rew:
        def __init__(self) -> None:
            self.dm_sent = False

    class _Session:
        def __init__(self) -> None:
            self.flushed = False

        async def flush(self) -> None:
            self.flushed = True

    rew_forbidden = _Rew()
    rew_prefs = _Rew()
    rew_zero = _Rew()
    gdate = date(2026, 8, 4)

    async def fake_load(session: Any, dates: set[date]) -> dict:
        return {
            (101, gdate): [
                {
                    "reward": rew_forbidden,
                    "exp": 10,
                    "gold": 5,
                    "items": [],
                    "dungeon_name": "A",
                    "rank": 1,
                    "party_size": 1,
                    "msg_total": 3,
                    "counted_msgs": 3,
                    "damage_total": 1,
                }
            ],
            (102, gdate): [
                {
                    "reward": rew_prefs,
                    "exp": 10,
                    "gold": 5,
                    "items": [],
                    "dungeon_name": "B",
                    "rank": 1,
                    "party_size": 1,
                    "msg_total": 2,
                    "counted_msgs": 2,
                    "damage_total": 1,
                }
            ],
            (103, gdate): [
                {
                    "reward": rew_zero,
                    "exp": 0,
                    "gold": 0,
                    "items": [],
                    "dungeon_name": "C",
                    "rank": 1,
                    "party_size": 1,
                    "msg_total": 0,
                    "counted_msgs": 0,
                    "damage_total": 0,
                }
            ],
        }

    async def fake_prefs(session: Any, uid: int, key: str) -> bool:
        return uid != 102

    class _Bot:
        async def send_message(self, **kwargs: Any) -> None:
            raise TelegramForbiddenError(
                method=SendMessage(chat_id=kwargs["chat_id"], text=kwargs["text"]),
                message="Forbidden: bot was blocked by the user",
            )

    monkeypatch.setattr(worker, "_load_unsent_reward_parts", fake_load)
    monkeypatch.setattr(worker, "msk_current_game_date", lambda: gdate)
    monkeypatch.setattr(
        "waifu_bot.services.player_notification_prefs.should_send_dm",
        fake_prefs,
    )

    session = _Session()
    sent_n, marked_n = asyncio.run(flush_daily_reward_dms(session, _Bot(), {gdate}))
    assert sent_n == 0
    assert marked_n == 3
    assert rew_forbidden.dm_sent is True
    assert rew_prefs.dm_sent is True
    assert rew_zero.dm_sent is True
    assert session.flushed is True
