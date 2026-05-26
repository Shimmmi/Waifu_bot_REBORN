"""Unit tests: expedition narrative anti-AI prompts and refine parsing."""
from __future__ import annotations

from waifu_bot.game.constants import (
    AI_NARRATIVE_ANTI_GENERIC_VERIFY_RU,
    AI_NARRATIVE_FINAL_MARKER,
    AI_NARRATIVE_GROTESQUE_HUMOR_RU,
    AI_NARRATIVE_HUMAN_RHYTHM_RU,
)
from waifu_bot.services.expedition_events_ai import (
    _extract_final_after_marker,
    _looks_like_refine_analysis,
    _resolve_refined_narrative,
)


def test_human_rhythm_constant_has_key_requirements() -> None:
    assert "ритм" in AI_NARRATIVE_HUMAN_RHYTHM_RU.lower()
    assert "фрагмент" in AI_NARRATIVE_HUMAN_RHYTHM_RU.lower()
    assert "живым" in AI_NARRATIVE_HUMAN_RHYTHM_RU.lower()


def test_anti_generic_verify_constant_requires_marker_only_output() -> None:
    assert "{draft}" in AI_NARRATIVE_ANTI_GENERIC_VERIFY_RU
    assert AI_NARRATIVE_FINAL_MARKER in AI_NARRATIVE_ANTI_GENERIC_VERIFY_RU
    lower = AI_NARRATIVE_ANTI_GENERIC_VERIFY_RU.lower()
    assert "мысленно" in lower
    assert "не выводи" in lower


def test_extract_final_after_marker() -> None:
    raw = (
        "Анализ: предложение 1 слишком шаблонное.\n"
        f"{AI_NARRATIVE_FINAL_MARKER}\n"
        "Паутина липнет к сапогам. Отряд не орёт — просто матерится тихо."
    )
    assert _extract_final_after_marker(raw) == (
        "Паутина липнет к сапогам. Отряд не орёт — просто матерится тихо."
    )


def test_extract_final_after_marker_uses_last_occurrence() -> None:
    raw = (
        f"Черновик упоминает {AI_NARRATIVE_FINAL_MARKER} в тексте.\n"
        f"{AI_NARRATIVE_FINAL_MARKER}\n"
        "Финальная версия."
    )
    assert _extract_final_after_marker(raw) == "Финальная версия."


def test_extract_final_after_marker_spaced_and_final_en() -> None:
    raw = "=== ФИНАЛ ===\nТекст на русском."
    assert _extract_final_after_marker(raw) == "Текст на русском."
    raw_en = "===FINAL===\nEnglish fallback."
    assert _extract_final_after_marker(raw_en) == "English fallback."


def test_extract_final_after_marker_missing_returns_none() -> None:
    assert _extract_final_after_marker("Только черновик без маркера.") is None
    assert _extract_final_after_marker("") is None


def test_looks_like_refine_analysis_detects_meta_response() -> None:
    analysis = (
        "Анализ: предложение generic.\n"
        "1) слишком шаблонно;\n"
        "2) нет конкретики."
    )
    assert _looks_like_refine_analysis(analysis) is True


def test_resolve_refined_narrative_rejects_analysis_without_marker() -> None:
    analysis = (
        "Анализ: предложение generic.\n"
        "1) слишком шаблонно;\n"
        "2) нет конкретики."
    )
    draft = "Отряд двинулся вперёд через туман."
    assert _resolve_refined_narrative(analysis, source_draft=draft) is None


def test_resolve_refined_narrative_returns_text_after_marker() -> None:
    draft = "Отряд двинулся вперёд через туман."
    raw = f"{AI_NARRATIVE_FINAL_MARKER}\nПаутина липнет к сапогам."
    assert _resolve_refined_narrative(raw, source_draft=draft) == "Паутина липнет к сапогам."


def test_verify_prompt_can_format_draft() -> None:
    draft = "Отряд двинулся вперёд через туман."
    prompt = AI_NARRATIVE_ANTI_GENERIC_VERIFY_RU.format(draft=draft)
    assert draft in prompt
    assert AI_NARRATIVE_GROTESQUE_HUMOR_RU not in prompt
