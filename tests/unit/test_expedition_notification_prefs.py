"""Unit tests: expedition DM prefs gate AI narratives and Telegram messages."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from waifu_bot.game.expedition_narrative_catalog import (
    EXPEDITION_LOCATION_ARCHETYPES,
    EXPEDITION_MODES,
    fallback_expedition_title,
    fallback_narrative_brief,
)
from waifu_bot.services.expedition import ExpeditionService, _apply_narrative_at_start


def test_apply_narrative_at_start_calls_openrouter_even_when_pref_off():
    async def _run():
        session = AsyncMock()
        active = MagicMock()
        active.id = 42
        active.player_id = 123

        waifu = MagicMock()
        waifu.name = "Alice"

        ai_brief = {
            "title": "Операция гнилая картошка",
            "setting_summary": "ai setting",
            "intro_narrative": "ai intro",
        }

        with (
            patch(
                "waifu_bot.services.player_notification_prefs.should_send_dm",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "waifu_bot.services.expedition_events_ai.generate_expedition_narrative_brief",
                new_callable=AsyncMock,
                return_value=ai_brief,
            ) as mock_brief,
            patch(
                "waifu_bot.services.expedition.fallback_narrative_brief",
            ) as mock_fallback,
        ):
            result = await _apply_narrative_at_start(
                session,
                active,
                location_archetype_id=None,
                expedition_mode_id=None,
                legacy_base_location="Ruins",
                affix_rows=[],
                squad=[waifu],
                events_total=4,
                duration_minutes=60,
            )

        assert result is None
        mock_brief.assert_called_once()
        mock_fallback.assert_not_called()
        assert active.narrative_brief["title"] == "Операция гнилая картошка"

    asyncio.run(_run())


def test_apply_narrative_at_start_uses_openrouter_when_pref_on():
    async def _run():
        session = AsyncMock()
        active = MagicMock()
        active.id = 42
        active.player_id = 123
        active.display_base_location = "Ruins"

        waifu = MagicMock()
        waifu.name = "Alice"

        ai_brief = {
            "title": "AI Title",
            "setting_summary": "ai setting",
            "intro_narrative": "ai intro",
        }

        with (
            patch(
                "waifu_bot.services.player_notification_prefs.should_send_dm",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "waifu_bot.services.expedition_events_ai.generate_expedition_narrative_brief",
                new_callable=AsyncMock,
                return_value=ai_brief,
            ) as mock_brief,
            patch(
                "waifu_bot.services.expedition_events_ai.format_expedition_start_intro_telegram",
                return_value="telegram intro",
            ) as mock_format,
        ):
            result = await _apply_narrative_at_start(
                session,
                active,
                location_archetype_id=None,
                expedition_mode_id=None,
                legacy_base_location="Ruins",
                affix_rows=[],
                squad=[waifu],
                events_total=4,
                duration_minutes=60,
            )

        assert result == "telegram intro"
        mock_brief.assert_called_once()
        mock_format.assert_called_once()

    asyncio.run(_run())


def test_fallback_narrative_brief_title_not_mode_archetype_template():
    desert = next(a for a in EXPEDITION_LOCATION_ARCHETYPES if a.id == "desert")
    social = next(m for m in EXPEDITION_MODES if m.id == "social")
    brief = fallback_narrative_brief(
        desert,
        social,
        4,
        affix_names=["Проклятая", "с огненными реками"],
        rng=__import__("random").Random(7),
    )
    title = brief["title"]
    assert "Социальная в Пустыня" not in title
    assert "Проклятая" not in title
    assert "огненными реками" not in title
    assert title.split()[0] in ("Операция", "Проект", "Рейд", "Миссия")


def test_fallback_expedition_title_is_deterministic_with_seed():
    desert = next(a for a in EXPEDITION_LOCATION_ARCHETYPES if a.id == "desert")
    social = next(m for m in EXPEDITION_MODES if m.id == "social")
    rng_a = __import__("random").Random(99)
    rng_b = __import__("random").Random(99)
    assert fallback_expedition_title(desert, social, rng_a) == fallback_expedition_title(
        desert, social, rng_b
    )


def test_process_due_ticks_silent_when_pref_off():
    async def _run():
        svc = ExpeditionService()
        session = AsyncMock()

        active = MagicMock()
        active.player_id = 999
        active.events_done = 0
        active.events_total = 4

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [active]
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        with (
            patch(
                "waifu_bot.services.player_notification_prefs.should_send_dm",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "waifu_bot.services.expedition.run_one_tick",
                new_callable=AsyncMock,
                return_value={"ok": True, "telegram_narrative": "", "telegram_status": ""},
            ) as mock_tick,
        ):
            out = await svc.process_due_ticks(session)

        mock_tick.assert_called_once()
        assert mock_tick.call_args.kwargs["silent"] is True
        assert out == []

    asyncio.run(_run())


def test_process_due_ticks_narrative_when_pref_on():
    async def _run():
        svc = ExpeditionService()
        session = AsyncMock()

        active = MagicMock()
        active.player_id = 999
        active.events_done = 0
        active.events_total = 4

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [active]
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        with (
            patch(
                "waifu_bot.services.player_notification_prefs.should_send_dm",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "waifu_bot.services.expedition.run_one_tick",
                new_callable=AsyncMock,
                return_value={
                    "ok": True,
                    "telegram_narrative": "story",
                    "telegram_status": "status",
                },
            ) as mock_tick,
        ):
            out = await svc.process_due_ticks(session)

        assert mock_tick.call_args.kwargs["silent"] is False
        assert out == [(999, "story", "status")]

    asyncio.run(_run())
