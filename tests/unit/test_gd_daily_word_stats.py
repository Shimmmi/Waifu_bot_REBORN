"""Unit tests: text_chars, phantom log, word AI parse/fallback, finale HTML/sort, privacy."""
from __future__ import annotations

import asyncio
import json

from waifu_bot.services.gd_daily_stats import (
    apply_message_to_day_stats,
    build_player_summary_rows,
    empty_day_stats,
    format_top_words_line_ru,
    normalize_day_stats,
    sort_rows_by_activity,
)
from waifu_bot.services.gd_daily_word_ai import (
    analyze_day_word_stats,
    local_top_words_for_user,
    merge_word_stats_into_rows,
    message_has_url,
    parse_word_stats_response,
)
from waifu_bot.services.gd_daily_worker import (
    build_daily_finale_html_chunks,
    format_daily_finale_stats_html,
)
from waifu_bot.services.gd_phantom_log import (
    MAX_CHARS_PER_MSG,
    MAX_MSGS_PER_USER,
    append_phantom_text,
    load_phantom_log,
    purge_phantom_log,
)
from waifu_bot.services.message_privacy import assert_no_user_message_text


class _Reg:
    def __init__(self, user_id: int, snap: dict, stats: dict | None = None):
        self.user_id = user_id
        self.waifu_snapshot = snap
        self.day_stats_json = stats


class _FakeRedis:
    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.ttls: dict[str, int] = {}

    async def llen(self, key: str) -> int:
        return len(self.lists.get(key, []))

    async def hget(self, key: str, field: str) -> str | None:
        return self.hashes.get(key, {}).get(str(field))

    async def rpush(self, key: str, value: str) -> int:
        self.lists.setdefault(key, []).append(value)
        return len(self.lists[key])

    async def hincrby(self, key: str, field: str, amount: int) -> int:
        h = self.hashes.setdefault(key, {})
        cur = int(h.get(str(field), "0")) + int(amount)
        h[str(field)] = str(cur)
        return cur

    async def expire(self, key: str, ttl: int) -> bool:
        self.ttls[key] = int(ttl)
        return True

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        items = self.lists.get(key, [])
        if end == -1:
            return list(items[start:])
        return list(items[start : end + 1])

    async def delete(self, *keys: str) -> int:
        n = 0
        for k in keys:
            if k in self.lists:
                del self.lists[k]
                n += 1
            if k in self.hashes:
                del self.hashes[k]
                n += 1
            self.ttls.pop(k, None)
        return n


def test_text_chars_accumulate_and_normalize():
    s = empty_day_stats()
    assert s["text_chars"] == 0
    s = apply_message_to_day_stats(s, msg_key="text", damage=1, text_chars_delta=12)
    s = apply_message_to_day_stats(s, msg_key="photo", damage=2, text_chars_delta=5)
    assert s["msg_total"] == 2
    assert s["text_chars"] == 17
    n = normalize_day_stats({"msg_total": 1, "by_type": {"text": 1}, "damage_total": 0})
    assert n["text_chars"] == 0
    assert_no_user_message_text(s)


def test_sort_rows_by_activity():
    rows = [
        {"user_id": 1, "msg_total": 2, "damage_total": 100},
        {"user_id": 2, "msg_total": 5, "damage_total": 10},
        {"user_id": 3, "msg_total": 5, "damage_total": 50},
    ]
    ordered = sort_rows_by_activity(rows)
    assert [r["user_id"] for r in ordered] == [3, 2, 1]


def test_local_top_words_and_no_repeat():
    stats = local_top_words_for_user(
        ["Привет мир и котики", "мир котики котики", "для котиков"]
    )
    assert stats["no_word_repeated"] is False
    words = [w["word"] for w in stats["top_words"]]
    # Lemmatized: котики/котиков → котик
    assert "котик" in words
    assert "и" not in words and "для" not in words

    uniq = local_top_words_for_user(["один два три", "четыре пять"])
    assert uniq["no_word_repeated"] is True
    assert uniq["top_words"] == []


def test_local_top_words_lemmas_case_forms_and_no_censor():
    """Different cases/numbers merge; profanity is counted (no blocklist)."""
    stats = local_top_words_for_user(["пидор", "пидора"])
    assert stats["no_word_repeated"] is False
    assert stats["words_unavailable"] is False
    assert stats["top_words"][0] == {"word": "пидор", "count": 2}

    cats = local_top_words_for_user(["котик бежал", "видел котика", "много котики"])
    by_word = {x["word"]: x["count"] for x in cats["top_words"]}
    assert by_word.get("котик", 0) >= 3
    assert "и" not in by_word and "для" not in by_word


def test_analyze_day_word_stats_is_local_only():
    out = asyncio.run(
        analyze_day_word_stats(
            {7: ["пидор", "пидора", "и", "для"]},
            timeout_sec=1.0,
        )
    )
    assert out[7]["top_words"][0] == {"word": "пидор", "count": 2}
    assert out[7]["no_word_repeated"] is False


def test_message_has_url_and_skip_link_messages():
    assert message_has_url("смотри https://www.youtube.com/shorts/abc123")
    assert message_has_url("www.example.com/foo")
    assert message_has_url("t.me/somechannel")
    assert message_has_url("youtube.com/shorts/xyz")
    assert not message_has_url("просто текст без ссылок играть")

    stats = local_top_words_for_user(
        [
            "https://www.youtube.com/shorts/abc https://www.youtube.com/shorts/def",
            "www.youtube.com/watch?v=1",
            "пидор",
            "пидора",
            "игра игра",
        ]
    )
    words = {x["word"]: x["count"] for x in stats["top_words"]}
    assert "https" not in words
    assert "www" not in words
    assert "youtube" not in words
    assert "com" not in words
    assert "shorts" not in words
    assert words.get("пидор") == 2
    assert words.get("игра") == 2


def test_parse_word_stats_response_json():
    raw = json.dumps(
        {
            "users": [
                {
                    "user_id": 10,
                    "top_words": [{"word": "игра", "count": 4}, {"word": "данж", "count": 2}],
                    "no_word_repeated": False,
                },
                {"user_id": 11, "top_words": [], "no_word_repeated": True},
            ]
        },
        ensure_ascii=False,
    )
    parsed = parse_word_stats_response(raw, {10, 11})
    assert parsed[10]["top_words"][0]["word"] == "игра"
    assert parsed[11]["no_word_repeated"] is True


def test_phantom_append_caps_and_purge():
    async def _run() -> None:
        redis = _FakeRedis()
        assert await append_phantom_text(redis, 1, 42, "  hello world  ")
        assert await append_phantom_text(redis, 1, 42, "") is False
        long = "x" * (MAX_CHARS_PER_MSG + 50)
        assert await append_phantom_text(redis, 1, 42, long)
        loaded = await load_phantom_log(redis, 1)
        assert 42 in loaded
        assert len(loaded[42][1]) == MAX_CHARS_PER_MSG

        # per-user cap
        redis2 = _FakeRedis()
        for i in range(MAX_MSGS_PER_USER):
            ok = await append_phantom_text(redis2, 2, 7, f"m{i}")
            assert ok
        assert await append_phantom_text(redis2, 2, 7, "overflow") is False
        assert len((await load_phantom_log(redis2, 2))[7]) == MAX_MSGS_PER_USER

        # cycle cap (patched smaller limit)
        import waifu_bot.services.gd_phantom_log as phantom_mod

        old_max = phantom_mod.MAX_ENTRIES_PER_CYCLE
        phantom_mod.MAX_ENTRIES_PER_CYCLE = 5
        try:
            redis3 = _FakeRedis()
            for i in range(5):
                assert await append_phantom_text(redis3, 3, i + 1, f"e{i}")
            assert await append_phantom_text(redis3, 3, 99, "nope") is False
        finally:
            phantom_mod.MAX_ENTRIES_PER_CYCLE = old_max

        await purge_phantom_log(redis, 1)
        assert await load_phantom_log(redis, 1) == {}

    asyncio.run(_run())


def test_day_stats_never_holds_message_body():
    s = apply_message_to_day_stats(
        empty_day_stats(),
        msg_key="text",
        damage=9,
        text_chars_delta=len("секретный текст игрока"),
    )
    assert "секретный" not in json.dumps(s, ensure_ascii=False)
    assert_no_user_message_text(s)
    battle_state = {"mode": "daily", "chat_msg_total": 1, "party": [{"user_id": 1}]}
    assert_no_user_message_text(battle_state)


def test_finale_html_includes_chars_damage_words_sorted():
    regs = [
        _Reg(
            1,
            {"name": "A", "username": "aaa"},
            {"msg_total": 2, "by_type": {"text": 2}, "damage_total": 10, "text_chars": 20},
        ),
        _Reg(
            2,
            {"name": "B", "username": "bbb"},
            {
                "msg_total": 8,
                "by_type": {"text": 5, "sticker": 3},
                "damage_total": 40,
                "text_chars": 100,
            },
        ),
    ]
    rows = build_player_summary_rows(regs, chat_msg_total=12)
    merge_word_stats_into_rows(
        rows,
        {
            2: {
                "top_words": [{"word": "кот", "count": 5}, {"word": "мир", "count": 3}],
                "no_word_repeated": False,
                "words_unavailable": False,
            },
            1: {"top_words": [], "no_word_repeated": True, "words_unavailable": False},
        },
    )
    html = format_daily_finale_stats_html(
        rows, chat_msg_total=12, dungeon_name="Тест", mvp=rows[1], least=rows[0]
    )
    # most active (B) first — waifu names only
    pos_b = html.index("<b>B</b>")
    pos_a = html.index("<b>A</b>")
    assert pos_b < pos_a
    assert "@" not in html
    assert "символов <b>100</b>" in html
    assert "урон <b>40</b>" in html
    assert "кот (5)" in html
    assert "нет повторов слов" not in html
    assert "медиа:" in html


def test_format_top_words_line_variants():
    assert format_top_words_line_ru({"words_unavailable": True, "msg_total": 2}) is None
    assert format_top_words_line_ru({"no_word_repeated": True, "msg_total": 2}) is None
    assert format_top_words_line_ru({"msg_total": 0, "text_chars": 0}) is None
    assert "а (3)" in (
        format_top_words_line_ru(
            {
                "msg_total": 3,
                "top_words": [{"word": "а", "count": 3}],
                "no_word_repeated": False,
            }
        )
        or ""
    )


def test_finale_chunks_split_on_soft_limit():
    rows = []
    for i in range(20):
        rows.append(
            {
                "user_id": i + 1,
                "username": f"u{i}",
                "name": f"N{i}",
                "msg_total": 20 - i,
                "chat_share_pct": 1.0,
                "text_chars": 50,
                "damage_total": 10,
                "by_type": {"text": 1},
                "top_words": [{"word": "слово", "count": 3}],
                "no_word_repeated": False,
                "words_unavailable": False,
            }
        )
    chunks = build_daily_finale_html_chunks(
        rows,
        chat_msg_total=100,
        dungeon_name="Длинный",
        mvp=rows[0],
        least=rows[-1],
        soft_limit=400,
    )
    assert len(chunks) >= 2
    assert all(len(c) <= 900 for c in chunks)


def test_merge_word_stats_missing_user():
    rows = [{"user_id": 5, "text_chars": 0, "msg_total": 0}]
    merge_word_stats_into_rows(rows, {})
    assert rows[0]["words_unavailable"] is False
    assert format_top_words_line_ru(rows[0]) is None
