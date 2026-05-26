"""Unit tests: expedition narrative prompts and review parser."""
from __future__ import annotations

from waifu_bot.game.constants import (
    AI_NARRATIVE_ANTI_GENERIC_REVIEW_PROMPT_RU,
    AI_NARRATIVE_HUMAN_RHYTHM_REQUIREMENTS_RU,
)
from waifu_bot.services.expedition_events_ai import (
    _extract_final_narrative_from_review,
    build_expedition_event_prompt,
    build_expedition_tick_prompt,
)


def test_tick_prompt_includes_rhythm_requirements() -> None:
    ctx = {
        "location": "Болото",
        "biome_tags": ["swamp"],
        "challenge": {"name": "Трясина", "category": "terrain", "level": 2},
        "squad": [{"name": "Аня", "class": "лучник"}],
        "outcome": "struggle",
        "event_num": 2,
        "total_events": 4,
        "is_final": False,
        "twist": None,
        "prev_summary": "Вчера топали по кочкам.",
        "squad_hp_ratio": 0.65,
    }
    prompt = build_expedition_tick_prompt(ctx)
    assert AI_NARRATIVE_HUMAN_RHYTHM_REQUIREMENTS_RU in prompt
    assert "Чередуй короткие и длинные предложения" in prompt
    assert "Болото" in prompt


def test_event_prompt_includes_rhythm_requirements() -> None:
    prompt = build_expedition_event_prompt(
        expedition_name="Тёмный лес",
        success=True,
        duration_minutes=60,
        squad_names=["Аня", "Бэль"],
        reward_gold=120,
        reward_experience=80,
    )
    assert AI_NARRATIVE_HUMAN_RHYTHM_REQUIREMENTS_RU in prompt
    assert "Тёмный лес" in prompt
    assert "120 золота" in prompt


def test_review_prompt_constant_has_final_marker_instruction() -> None:
    assert "===ИТОГ===" in AI_NARRATIVE_ANTI_GENERIC_REVIEW_PROMPT_RU
    assert "шаблонным" in AI_NARRATIVE_ANTI_GENERIC_REVIEW_PROMPT_RU


def test_extract_final_narrative_from_review_marker() -> None:
    raw = (
        "Анализ: первое предложение шаблонное.\n\n"
        "===ИТОГ===\n"
        "Когти царапнули щит. Аня выдохнула — и только тогда поняла, что дрожит."
    )
    assert _extract_final_narrative_from_review(raw) == (
        "Когти царапнули щит. Аня выдохнула — и только тогда поняла, что дрожит."
    )


def test_extract_final_narrative_from_review_heading_fallback() -> None:
    raw = (
        "Разбор по предложениям...\n\n"
        "Полностью переписанная версия:\n"
        "Грязь до колен. Смеялись — потому что иначе страшнее."
    )
    assert _extract_final_narrative_from_review(raw) == (
        "Грязь до колен. Смеялись — потому что иначе страшнее."
    )


def test_extract_final_narrative_from_review_last_paragraph_fallback() -> None:
    raw = "Длинный анализ первого абзаца с кучей текста.\n\nКороткий финал без маркера."
    assert _extract_final_narrative_from_review(raw) == "Короткий финал без маркера."


def test_extract_final_narrative_from_review_empty() -> None:
    assert _extract_final_narrative_from_review("") is None
    assert _extract_final_narrative_from_review("   ") is None
