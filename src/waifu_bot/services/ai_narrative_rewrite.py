"""Shared rhythm-rewrite pass and output sanitization for AI narratives."""

from __future__ import annotations

import logging
import re

import httpx

from waifu_bot.core.config import settings
from waifu_bot.game.constants import AI_NARRATIVE_RHYTHM_REWRITE_RU
from waifu_bot.services.ai_presets import SinglePreset, resolve_preset
from waifu_bot.services.llm_client import has_text_llm_configured, post_chat_completions_routerai

logger = logging.getLogger(__name__)


def strip_code_fence(raw: str) -> str:
    text = (raw or "").strip()
    fence = re.match(r"^```(?:\w+)?\s*([\s\S]*?)\s*```\s*$", text, re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    return text


def strip_markdown_prose(text: str) -> str:
    s = (text or "").strip()
    s = re.sub(r"^#+\s*", "", s, flags=re.MULTILINE)
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"\*([^*]+)\*", r"\1", s)
    s = re.sub(r"^---+\s*$", "", s, flags=re.MULTILINE)
    return s.strip()


def strip_analysis_headers(text: str) -> str:
    """Убрать markdown-заголовки, сохраняя HTML-теги."""
    s = (text or "").strip()
    s = re.sub(r"^#+\s*.*$", "", s, flags=re.MULTILINE)
    s = re.sub(r"^---+\s*$", "", s, flags=re.MULTILINE)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def looks_like_meta_analysis(text: str) -> bool:
    """Meta-разбор вместо прозы — не отправлять в чат."""
    raw = (text or "").strip()
    if not raw:
        return False
    lower = raw.lower()
    markers = (
        "### анализ",
        "анализ предложений",
        "**почему generic",
        "почему generic:",
        "оригинальное наблюдение",
        "клише из генератора",
        "генератора текстов",
        "штамп",
    )
    if any(m in lower for m in markers):
        return True
    if re.search(r"\*\*\s*1\.", raw) or re.search(r"\n\s*1\)", raw):
        if "generic" in lower or "анализ" in lower:
            return True
    return False


def extract_prose_after_rewrite_header(text: str) -> str | None:
    """Если модель вывела разбор + «Переписанный текст», берём только прозу."""
    raw = (text or "").strip()
    if not raw:
        return None
    for pattern in (
        r"(?:^|\n)#+\s*Переписанный текст\s*\n",
        r"(?:^|\n)Переписанный текст\s*\n",
    ):
        matches = list(re.finditer(pattern, raw, re.IGNORECASE))
        if matches:
            chunk = raw[matches[-1].end() :].strip()
            if chunk:
                return chunk
    parts = re.split(r"\n---+\n", raw)
    if len(parts) > 1:
        tail = parts[-1].strip()
        if tail:
            return tail
    return None


def sanitize_rhythm_rewrite_output(
    raw: str,
    *,
    source_draft: str,
    preserve_html: bool = False,
) -> str | None:
    """Возвращает только прозу rewrite или None (fallback на draft)."""
    text = strip_code_fence(raw)
    if not text:
        return None
    extracted = extract_prose_after_rewrite_header(text)
    candidate = extracted if extracted else text
    if preserve_html:
        candidate = strip_analysis_headers(candidate)
    else:
        candidate = strip_markdown_prose(candidate)
    if not candidate:
        return None
    if looks_like_meta_analysis(candidate):
        return None
    draft = (source_draft or "").strip()
    draft_len = len(draft)
    if draft_len > 0 and len(candidate) < max(20, int(draft_len * 0.4)) and len(candidate) < 40:
        return None
    return candidate


def _html_escape_plain(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def escape_telegram_html(text: str) -> str:
    """Экранирует &, <, > вне пар <b>...</b> для Telegram HTML."""
    raw = text or ""
    if not raw:
        return ""
    parts: list[str] = []
    last = 0
    for m in re.finditer(r"<b>(.*?)</b>", raw, re.IGNORECASE | re.DOTALL):
        before = raw[last : m.start()]
        if before:
            parts.append(_html_escape_plain(before))
        inner = m.group(1)
        parts.append(f"<b>{_html_escape_plain(inner)}</b>")
        last = m.end()
    parts.append(_html_escape_plain(raw[last:]))
    return "".join(parts)


def _openrouter_text_extra() -> dict[str, object]:
    return {"reasoning": {"exclude": True}}


def _extract_openrouter_assistant_text(choice: object) -> str:
    if not isinstance(choice, dict):
        return ""
    msg = choice.get("message")
    if isinstance(msg, dict):
        raw = msg.get("content")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        if isinstance(raw, list):
            parts: list[str] = []
            for block in raw:
                if isinstance(block, str) and block.strip():
                    parts.append(block.strip())
                elif isinstance(block, dict):
                    for key in ("text", "output_text", "content"):
                        val = block.get(key)
                        if isinstance(val, str) and val.strip():
                            parts.append(val.strip())
                            break
            if parts:
                return "\n".join(parts).strip()
        reasoning = msg.get("reasoning")
        if isinstance(reasoning, str) and reasoning.strip():
            return reasoning.strip()
    t = choice.get("text")
    if isinstance(t, str) and t.strip():
        return t.strip()
    return ""


async def rhythm_rewrite_narrative(
    draft: str,
    *,
    caller: str,
    length_hint: str,
    preserve_html: bool = False,
    max_tokens: int = 320,
) -> str:
    """
    Второй проход OpenRouter: rhythm-rewrite без meta-анализа.
    При сбое возвращает исходный draft.
    """
    source = (draft or "").strip()
    if not source:
        return draft
    if not has_text_llm_configured():
        return draft

    html_note = ""
    if preserve_html:
        html_note = (
            " Сохрани все теги <b>...</b> и абзацы (пустые строки между блоками). "
            "Не добавляй другие HTML-теги."
        )

    try:
        fast_cfg, _ = resolve_preset("fast")
        model = fast_cfg.model if isinstance(fast_cfg, SinglePreset) else "google/gemini-3.5-flash"
    except Exception:
        model = "google/gemini-3.5-flash"

    prompt = (
        AI_NARRATIVE_RHYTHM_REWRITE_RU.format(draft=source, length_hint=length_hint)
        + html_note
    )

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            r = await post_chat_completions_routerai(
                client,
                {
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max(128, int(max_tokens)),
                    "temperature": 0.72,
                    **_openrouter_text_extra(),
                },
                model=model,
                caller=f"rhythm rewrite ({caller})",
            )
            if r.status_code != 200:
                logger.warning(
                    "LLM rhythm rewrite (%s): HTTP %s body=%s",
                    caller,
                    r.status_code,
                    (r.text or "")[:400],
                )
                return draft
            data = r.json()
            choices = data.get("choices") or []
            if not isinstance(choices, list) or not choices:
                return draft
            text = _extract_openrouter_assistant_text(choices[0])
            if not text:
                logger.warning("OpenRouter rhythm rewrite (%s): пустой ответ", caller)
                return draft
            resolved = sanitize_rhythm_rewrite_output(
                text,
                source_draft=source,
                preserve_html=preserve_html,
            )
            if resolved:
                if preserve_html:
                    return escape_telegram_html(resolved)
                return resolved
            logger.warning(
                "OpenRouter rhythm rewrite (%s): no valid prose, using draft; prefix=%s",
                caller,
                text[:120].replace("\n", " "),
            )
            return escape_telegram_html(source) if preserve_html else draft
    except Exception as e:
        logger.warning("OpenRouter rhythm rewrite (%s) error: %s", caller, e)
        return escape_telegram_html(source) if preserve_html else draft
