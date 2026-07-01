"""Unit tests: expedition narrative rhythm-rewrite prompts and sanitization."""
from __future__ import annotations

from waifu_bot.game.constants import (
    AI_NARRATIVE_GROTESQUE_HUMOR_RU,
    AI_NARRATIVE_RHYTHM_REWRITE_RU,
)
from waifu_bot.services.ai_narrative_rewrite import (
    looks_like_meta_analysis,
    sanitize_rhythm_rewrite_output,
)


def test_rhythm_rewrite_prompt_has_text_placeholder() -> None:
    assert "{draft}" in AI_NARRATIVE_RHYTHM_REWRITE_RU
    assert "{length_hint}" in AI_NARRATIVE_RHYTHM_REWRITE_RU
    assert "TEXT:" in AI_NARRATIVE_RHYTHM_REWRITE_RU
    lower = AI_NARRATIVE_RHYTHM_REWRITE_RU.lower()
    assert "natural human rhythm" in lower
    assert "без анализа" in lower
    assert "===финал===" not in lower


def test_rhythm_rewrite_prompt_can_format() -> None:
    draft = "Отряд двинулся вперёд через туман."
    prompt = AI_NARRATIVE_RHYTHM_REWRITE_RU.format(draft=draft, length_hint="2–4 предложения")
    assert draft in prompt
    assert AI_NARRATIVE_GROTESQUE_HUMOR_RU not in prompt


def test_looks_like_meta_analysis_detects_chat_example() -> None:
    analysis = (
        "Вот анализ предложений, которые звучат как «клише из генератора текстов»:\n\n"
        "### Анализ\n\n"
        "**1. «Жить захочешь — не так раскорячишься»**\n"
        "*   **Почему generic:** Это заезженная цитата...\n"
    )
    assert looks_like_meta_analysis(analysis) is True


def test_sanitize_rejects_analysis_only() -> None:
    analysis = (
        "### Анализ\n\n"
        "**1. фраза**\n"
        "*   **Почему generic:** штамп.\n"
    )
    draft = "Кондуктор требовал проездной, пока отряд мёрз."
    assert sanitize_rhythm_rewrite_output(analysis, source_draft=draft) is None


def test_sanitize_extracts_prose_after_rewrite_header() -> None:
    raw = (
        "### Анализ\n\n"
        "**1. фраза**\n"
        "*   **Почему generic:** штамп.\n\n"
        "---\n\n"
        "### Переписанный текст\n\n"
        "Кондуктор — облупившийся механизм в форменной фуражке — упрямо требовал проездной."
    )
    draft = "Кондуктор требовал проездной, пока отряд превращался в ледяные изваяния."
    assert sanitize_rhythm_rewrite_output(raw, source_draft=draft) == (
        "Кондуктор — облупившийся механизм в форменной фуражке — упрямо требовал проездной."
    )


def test_sanitize_accepts_clean_rewrite() -> None:
    draft = "Отряд двинулся вперёд через туман."
    rewrite = "Туман сглотнул отряд. Шаги — редкие. Впереди — только серость."
    assert sanitize_rhythm_rewrite_output(rewrite, source_draft=draft) == rewrite


def test_sanitize_rejects_truncated_short_tail() -> None:
    draft = "Кондуктор требовал проездной, пока отряд превращался в ледяные изваяния, оплакивая каждый вдох."
    truncated = "Кондуктор — облуп"
    assert sanitize_rhythm_rewrite_output(truncated, source_draft=draft) is None
