"""Unit tests: expedition narrative anti-AI prompts and refine parsing."""
from __future__ import annotations

from waifu_bot.game.constants import (
    AI_NARRATIVE_ANTI_GENERIC_VERIFY_RU,
    AI_NARRATIVE_FINAL_MARKER,
    AI_NARRATIVE_GROTESQUE_HUMOR_RU,
    AI_NARRATIVE_HUMAN_RHYTHM_RU,
)
from waifu_bot.services.expedition_events_ai import _extract_final_after_marker


def test_human_rhythm_constant_has_key_requirements() -> None:
    assert "ритм" in AI_NARRATIVE_HUMAN_RHYTHM_RU.lower()
    assert "фрагмент" in AI_NARRATIVE_HUMAN_RHYTHM_RU.lower()
    assert "живым" in AI_NARRATIVE_HUMAN_RHYTHM_RU.lower()


def test_anti_generic_verify_constant_has_marker_and_draft_placeholder() -> None:
    assert "{draft}" in AI_NARRATIVE_ANTI_GENERIC_VERIFY_RU
    assert AI_NARRATIVE_FINAL_MARKER in AI_NARRATIVE_ANTI_GENERIC_VERIFY_RU
    assert "generic" in AI_NARRATIVE_ANTI_GENERIC_VERIFY_RU.lower()


def test_extract_final_after_marker() -> None:
    raw = (
        "Анализ: предложение 1 слишком шаблонное.\n"
        f"{AI_NARRATIVE_FINAL_MARKER}\n"
        "Паутина липнет к сапогам. Отряд не орёт — просто матерится тихо."
    )
    assert _extract_final_after_marker(raw) == (
        "Паутина липнет к сапогам. Отряд не орёт — просто матерится тихо."
    )


def test_extract_final_after_marker_missing_returns_none() -> None:
    assert _extract_final_after_marker("Только черновик без маркера.") is None
    assert _extract_final_after_marker("") is None


def test_verify_prompt_can_format_draft() -> None:
    draft = "Отряд двинулся вперёд через туман."
    prompt = AI_NARRATIVE_ANTI_GENERIC_VERIFY_RU.format(draft=draft)
    assert draft in prompt
    assert AI_NARRATIVE_GROTESQUE_HUMOR_RU not in prompt
