"""Unit tests: shared AI narrative rhythm-rewrite sanitization."""
from __future__ import annotations

from waifu_bot.services.ai_narrative_rewrite import (
    escape_telegram_html,
    extract_prose_after_rewrite_header,
    looks_like_meta_analysis,
    sanitize_rhythm_rewrite_output,
)


def test_preserve_html_keeps_b_tags() -> None:
    draft = "<b>Путютя</b> бьёт <b>Паучка</b> навыком <b>Раскол</b> (урон)."
    rewrite = "<b>Путютя</b> с рыком обрушивает <b>Раскол</b> (урон) на <b>Паучка</b>."
    assert sanitize_rhythm_rewrite_output(rewrite, source_draft=draft, preserve_html=True) == rewrite


def test_preserve_html_rejects_meta_analysis() -> None:
    analysis = (
        "### Анализ\n\n"
        "**1. фраза**\n"
        "*   **Почему generic:** штамп.\n"
    )
    draft = "<b>Алиса</b> атакует монстра."
    assert sanitize_rhythm_rewrite_output(analysis, source_draft=draft, preserve_html=True) is None


def test_extract_prose_after_rewrite_header() -> None:
    raw = (
        "### Анализ\n\n"
        "**1. фраза**\n\n"
        "---\n\n"
        "### Переписанный текст\n\n"
        "<b>Алиса</b> взмахнула посохом."
    )
    assert extract_prose_after_rewrite_header(raw) == "<b>Алиса</b> взмахнула посохом."


def test_escape_telegram_html_preserves_b_tags() -> None:
    text = "<b>Алиса</b> & <script> vs <b>Бэль</b>"
    assert escape_telegram_html(text) == (
        "<b>Алиса</b> &amp; &lt;script&gt; vs <b>Бэль</b>"
    )


def test_looks_like_meta_analysis() -> None:
    assert looks_like_meta_analysis("### Анализ\n**Почему generic:** штамп") is True
    assert looks_like_meta_analysis("<b>Алиса</b> бьёт монстра.") is False
