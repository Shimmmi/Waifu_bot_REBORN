"""Unit tests for guild raid v2 narrative AI."""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from waifu_bot.game.constants import RAID_V2_SLOT_COUNT
from waifu_bot.services.guild_raid_narrative_ai import (
    _bold_proper_nouns,
    _build_compose_fallback_narrative,
    _format_last_tactic_story,
    _parse_tactics_json,
    _slot_summary,
    _strip_leaked_json,
    compose_raid_daily_narrative,
    generate_raid_daily_narrative,
    generate_raid_daily_tactics,
    generate_raid_slot_summary,
    msk_slot_index_for_dt,
    msk_slot_label,
)
from waifu_bot.services.guild_raid_v2_service import (
    _poll_log_matches,
    _slot_label,
    aggregate_chat_slots,
    deliver_raid_daily,
)


def _scalar_result(value):
    r = MagicMock()
    r.scalars.return_value.all.return_value = value
    return r


def test_msk_4h_slot_labels():
    assert msk_slot_label(0) == "00:00–03:59 МСК"
    assert msk_slot_label(5) == "20:00–23:59 МСК"
    assert _slot_label(2) == "08:00–11:59 МСК"


def test_msk_slot_index_for_dt():
    dt = datetime(2026, 6, 7, 9, 30, tzinfo=timezone.utc)
    idx = msk_slot_index_for_dt(dt)
    assert 0 <= idx < RAID_V2_SLOT_COUNT


def test_strip_leaked_json():
    raw = '<b>Story</b> {"tactics":[{"label":"x","risk":"low","terrain_fit":["cave"]}]}'
    cleaned = _strip_leaked_json(raw)
    assert "tactics" not in cleaned
    assert "Story" in cleaned


def test_bold_proper_nouns():
    text = "Stonks и Alice идут в Лес Теней"
    out = _bold_proper_nouns(
        text,
        party=[{"name": "Stonks"}, {"name": "Alice"}],
        location="Лес Теней",
        guild_tag="TST",
    )
    assert "<b>Stonks</b>" in out
    assert "<b>Alice</b>" in out
    assert "<b>Лес Теней</b>" in out


def test_parse_tactics_json():
    raw = '{"tactics":[{"label":"A","risk":"low","terrain_fit":["swamp"]},{"label":"B","risk":"high","terrain_fit":["swamp"]},{"label":"C","risk":"medium","terrain_fit":["swamp"]}]}'
    tactics = _parse_tactics_json(raw)
    assert len(tactics) == 3
    assert tactics[0]["label"] == "A"


def test_slot_summary_all_rest():
    beats = [
        {"slot_index": i, "slot_label": msk_slot_label(i), "rest": True, "active_players": [], "previews": []}
        for i in range(RAID_V2_SLOT_COUNT)
    ]
    text = _slot_summary(beats)
    assert "Неактивные слоты" in text or "привал" in text.lower()


def test_build_compose_fallback_one_paragraph_when_no_activity():
    text = _build_compose_fallback_narrative(
        day_index=1,
        loc="Город на мосту",
        slot_summaries=[],
        company_vitality=100,
        story_progress=0,
    )
    assert "спокойные сутки" in text


def test_generate_raid_daily_narrative_fallback_without_llm():
    async def _run():
        with patch("waifu_bot.services.guild_raid_narrative_ai.has_llm_configured", return_value=False):
            narrative, tactics = await generate_raid_daily_narrative(
                guild_name="Test Guild",
                guild_tag="lolol",
                day_index=1,
                location_archetype_id="bridge_town",
                narrative_style_id=0,
                party=[
                    {
                        "player_id": 1,
                        "name": "Stonks",
                        "class_id": 1,
                        "race_id": 1,
                        "level": 10,
                    }
                ],
                slot_beats=[
                    {
                        "slot_index": 0,
                        "slot_label": "00:00–03:59 МСК",
                        "rest": False,
                        "active_players": ["Stonks (1)"],
                        "previews": ["hi"],
                    }
                ],
                company_vitality=100,
                story_progress=0,
                last_tactic=None,
                last_resolve=None,
                chronicle_summaries=[],
            )
        assert narrative
        assert "День 1" in narrative
        assert len(tactics) >= 3
        assert all(t.get("label") for t in tactics)

    asyncio.run(_run())


def test_format_last_tactic_story_includes_label():
    text = _format_last_tactic_story(
        {"label": "Обход с фланга"},
        {"vitality_delta": -5, "progress_delta": 8},
    )
    assert "Обход с фланга" in text
    assert "вымотан" in text.lower() or "Силы" in text


def test_rest_slot_summary_skips_llm():
    async def _run():
        with patch(
            "waifu_bot.services.guild_raid_narrative_ai._call_llm_raw",
            new_callable=AsyncMock,
        ) as llm_mock:
            out = await generate_raid_slot_summary(
                guild_name="G",
                guild_tag="T",
                location_archetype_id="bridge_town",
                party=[{"name": "A"}],
                slot_label="00:00–03:59 МСК",
                slot_beat={
                    "rest": True,
                    "active_players": [],
                    "previews": [],
                },
            )
        llm_mock.assert_not_awaited()
        assert "молчал" in out.lower() or "привал" in out.lower()

    asyncio.run(_run())


def test_compose_includes_tactic_in_prompt():
    async def _run():
        with patch(
            "waifu_bot.services.guild_raid_narrative_ai._call_llm_raw",
            new_callable=AsyncMock,
            return_value="Draft",
        ) as raw_mock, patch(
            "waifu_bot.services.guild_raid_narrative_ai._finalize_narrative_html",
            new_callable=AsyncMock,
            return_value="Final",
        ):
            await compose_raid_daily_narrative(
                guild_name="G",
                guild_tag="T",
                day_index=2,
                location_archetype_id="forest",
                party=[{"name": "Bob", "class_id": 1, "race_id": 1, "level": 1}],
                slot_summaries=[{"slot_index": 0, "slot_label": "00:00", "summary_html": "x"}],
                company_vitality=90,
                story_progress=10,
                last_tactic={"label": "Обход с фланга"},
                last_resolve={"vitality_delta": -3, "progress_delta": 6},
                chronicle_summaries=[],
                adventure_goal="найти артефакт",
            )
        prompt = raw_mock.await_args.args[0]
        assert "Обход с фланга" in prompt
        assert "найти артефакт" in prompt

    asyncio.run(_run())


def test_compose_strips_json_from_llm_output():
    async def _run():
        leaked = 'Summary text {"tactics":[{"label":"x"}]}'
        with patch(
            "waifu_bot.services.guild_raid_narrative_ai._call_llm_raw",
            new_callable=AsyncMock,
            return_value=leaked,
        ), patch(
            "waifu_bot.services.guild_raid_narrative_ai._finalize_narrative_html",
            new_callable=AsyncMock,
            return_value="Summary text",
        ):
            out = await compose_raid_daily_narrative(
                guild_name="G",
                guild_tag="T",
                day_index=2,
                location_archetype_id="forest",
                party=[{"name": "Bob", "class_id": 1, "race_id": 1, "level": 1}],
                slot_summaries=[{"slot_index": 0, "slot_label": "00:00", "summary_html": "x"}],
                company_vitality=90,
                story_progress=10,
                last_tactic=None,
                last_resolve=None,
                chronicle_summaries=[],
            )
        assert "tactics" not in out

    asyncio.run(_run())


def test_generate_raid_daily_tactics_fallback():
    async def _run():
        with patch("waifu_bot.services.guild_raid_narrative_ai.has_llm_configured", return_value=False):
            tactics = await generate_raid_daily_tactics(
                guild_name="G",
                guild_tag="T",
                day_index=1,
                location_archetype_id="forest",
                party=[],
                narrative_preview="summary",
                last_tactic=None,
            )
        assert len(tactics) >= 3

    asyncio.run(_run())


def test_poll_log_matches_group_only():
    pv = {
        "group_poll_id": "abc",
        "__telegram_poll_id__": "abc",
        "votes": {},
    }
    assert _poll_log_matches(pv, "abc")
    assert not _poll_log_matches(pv, "zzz")


def test_poll_log_matches_group_and_dm_legacy():
    pv = {
        "group_poll_id": "abc",
        "__telegram_poll_id__": "abc",
        "dm_poll_ids": {"123": "dm456"},
        "votes": {},
    }
    assert _poll_log_matches(pv, "abc")
    assert _poll_log_matches(pv, "dm456")
    assert not _poll_log_matches(pv, "zzz")


def test_deliver_poll_group_only():
    async def _run():
        from zoneinfo import ZoneInfo

        msk = ZoneInfo("Europe/Moscow")
        log = SimpleNamespace(
            id=1,
            raid_id=10,
            day_index=1,
            narrative_html="Hello",
            tactic_poll_options_json=[{"label": "A"}],
            delivered_at=None,
            poll_message_id=None,
            poll_chat_id=None,
            poll_deadline_at=None,
            poll_votes_json=None,
        )
        raid = SimpleNamespace(
            id=10,
            status="active",
            day_index=0,
            guild_id=1,
            started_at=datetime(2026, 6, 7, 12, 0, tzinfo=msk),
        )
        guild = SimpleNamespace(id=1, telegram_chat_id=-100)
        session = AsyncMock()
        session.get = AsyncMock(side_effect=lambda model, pk: raid if pk == 10 else guild)
        claim_result = MagicMock()
        claim_result.scalar_one_or_none.return_value = 1
        session.execute = AsyncMock(return_value=claim_result)
        session.refresh = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        bot = AsyncMock()
        poll_msg = SimpleNamespace(message_id=99, poll=SimpleNamespace(id="poll1"))
        bot.send_message = AsyncMock()
        bot.send_poll = AsyncMock(return_value=poll_msg)

        with patch("waifu_bot.services.webhook.get_bot", return_value=bot):
            await deliver_raid_daily(session, log)

        assert bot.send_poll.await_count == 1
        assert log.poll_votes_json.get("group_poll_id") == "poll1"
        assert "dm_poll_ids" not in log.poll_votes_json

    asyncio.run(_run())


def test_deliver_raid_daily_idempotent_claim():
    async def _run():
        log = SimpleNamespace(
            id=1,
            raid_id=10,
            day_index=1,
            narrative_html="Hello",
            tactic_poll_options_json=[{"label": "A"}],
            delivered_at=None,
            poll_message_id=None,
            poll_chat_id=None,
            poll_deadline_at=None,
            poll_votes_json=None,
        )
        raid = SimpleNamespace(id=10, status="active", day_index=0, guild_id=1)
        guild = SimpleNamespace(id=1, telegram_chat_id=-100)
        session = AsyncMock()
        session.get = AsyncMock(side_effect=lambda model, pk: raid if pk == 10 else guild)
        claim_result = MagicMock()
        claim_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=claim_result)
        session.refresh = AsyncMock()
        session.flush = AsyncMock()

        await deliver_raid_daily(session, log)
        session.execute.assert_awaited()

    asyncio.run(_run())


def test_aggregate_chat_slots_respects_min_event_ts():
    async def _run():
        raid = SimpleNamespace(party_snapshot_json=[{"player_id": 1, "name": "Alice"}])
        ev_new = SimpleNamespace(
            player_id=1,
            event_ts=datetime(2026, 6, 7, 18, 0, tzinfo=timezone.utc),
            text_preview="after raid",
        )
        session = AsyncMock()
        session.get = AsyncMock(return_value=raid)
        session.execute = AsyncMock(return_value=_scalar_result([ev_new]))

        min_ts = datetime(2026, 6, 7, 15, 0, tzinfo=timezone.utc)
        slots = await aggregate_chat_slots(
            session,
            raid_id=1,
            for_date=date(2026, 6, 7),
            min_event_ts=min_ts,
        )
        active = [s for s in slots if not s["rest"]]
        assert len(active) == 1
        assert active[0]["previews"] == ["after raid"]

    asyncio.run(_run())
