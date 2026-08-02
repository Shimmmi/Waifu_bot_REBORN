"""End-of-day top-5 word stats via RouterAI (+ local fallback).

Consumes the phantom Redis log only; never persists raw message bodies.
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from typing import Any

from waifu_bot.core.config import settings
from waifu_bot.services.ai_service import generate as ai_generate
from waifu_bot.services.llm_client import has_text_llm_configured

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ]{2,}", re.UNICODE)

# Russian prepositions / conjunctions / particles (and common English fillers).
_STOPWORDS = frozenset(
    {
        "а",
        "без",
        "бы",
        "был",
        "была",
        "были",
        "было",
        "быть",
        "в",
        "вам",
        "вас",
        "ведь",
        "во",
        "вот",
        "все",
        "всего",
        "всех",
        "вы",
        "где",
        "да",
        "даже",
        "для",
        "до",
        "его",
        "ее",
        "ей",
        "ему",
        "если",
        "есть",
        "еще",
        "ещё",
        "же",
        "за",
        "здесь",
        "и",
        "из",
        "или",
        "им",
        "их",
        "к",
        "как",
        "когда",
        "кто",
        "ли",
        "либо",
        "мне",
        "мной",
        "может",
        "мы",
        "на",
        "над",
        "надо",
        "не",
        "него",
        "нее",
        "ней",
        "нет",
        "ни",
        "но",
        "ну",
        "о",
        "об",
        "однако",
        "он",
        "она",
        "они",
        "оно",
        "от",
        "перед",
        "по",
        "под",
        "после",
        "при",
        "про",
        "с",
        "со",
        "так",
        "также",
        "там",
        "то",
        "тогда",
        "того",
        "тоже",
        "той",
        "только",
        "том",
        "тот",
        "ты",
        "у",
        "уже",
        "хотя",
        "чего",
        "чем",
        "через",
        "что",
        "чтобы",
        "это",
        "этого",
        "этой",
        "этом",
        "этот",
        "я",
        "and",
        "or",
        "the",
        "a",
        "an",
        "to",
        "of",
        "in",
        "on",
        "for",
        "with",
        "is",
        "are",
        "was",
        "were",
        "be",
        "as",
        "at",
        "by",
        "from",
    }
)

_BATCH_USERS = 10


def local_top_words_for_user(messages: list[str], *, top_n: int = 5) -> dict[str, Any]:
    """Naive frequency fallback: lowercased tokens, stopwords dropped, no morphology."""
    counts: Counter[str] = Counter()
    for msg in messages or []:
        for tok in _WORD_RE.findall(msg or ""):
            w = tok.lower().replace("ё", "е")
            if w in _STOPWORDS:
                continue
            counts[w] += 1
    if not counts:
        return {"top_words": [], "no_word_repeated": False, "words_unavailable": True}
    if max(counts.values()) <= 1:
        return {"top_words": [], "no_word_repeated": True, "words_unavailable": False}
    top = [{"word": w, "count": int(c)} for w, c in counts.most_common(top_n)]
    return {"top_words": top, "no_word_repeated": False, "words_unavailable": False}


def local_word_stats(log_by_user: dict[int, list[str]]) -> dict[int, dict[str, Any]]:
    return {int(uid): local_top_words_for_user(msgs) for uid, msgs in (log_by_user or {}).items()}


def parse_word_stats_response(raw: str | None, expected_uids: set[int]) -> dict[int, dict[str, Any]]:
    """Parse RouterAI JSON into per-user word stats. Invalid/missing users omitted."""
    out: dict[int, dict[str, Any]] = {}
    if not raw or not str(raw).strip():
        return out
    text = str(raw).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except Exception:
        # Try to extract first JSON object
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return out
        try:
            data = json.loads(m.group(0))
        except Exception:
            return out
    users = data.get("users") if isinstance(data, dict) else None
    if not isinstance(users, list):
        return out
    for item in users:
        if not isinstance(item, dict):
            continue
        try:
            uid = int(item.get("user_id"))
        except (TypeError, ValueError):
            continue
        if expected_uids and uid not in expected_uids:
            continue
        no_rep = bool(item.get("no_word_repeated"))
        words_raw = item.get("top_words") or []
        words: list[dict[str, Any]] = []
        if isinstance(words_raw, list):
            for w in words_raw[:5]:
                if isinstance(w, dict):
                    word = str(w.get("word") or "").strip()
                    try:
                        count = int(w.get("count") or 0)
                    except (TypeError, ValueError):
                        count = 0
                    if word:
                        words.append({"word": word, "count": max(0, count)})
                else:
                    word = str(w).strip()
                    if word:
                        words.append({"word": word, "count": 0})
        max_count = max((int(x.get("count") or 0) for x in words), default=0)
        if no_rep or (words and max_count <= 1):
            out[uid] = {
                "top_words": [],
                "no_word_repeated": True,
                "words_unavailable": False,
            }
        elif words:
            out[uid] = {
                "top_words": words[:5],
                "no_word_repeated": False,
                "words_unavailable": False,
            }
        else:
            out[uid] = {
                "top_words": [],
                "no_word_repeated": False,
                "words_unavailable": True,
            }
    return out


def _chunk_users(log_by_user: dict[int, list[str]], size: int = _BATCH_USERS) -> list[dict[int, list[str]]]:
    items = list(log_by_user.items())
    if not items:
        return []
    chunks: list[dict[int, list[str]]] = []
    for i in range(0, len(items), size):
        chunks.append(dict(items[i : i + size]))
    return chunks


def _build_prompt(batch: dict[int, list[str]]) -> str:
    payload = {str(uid): msgs for uid, msgs in batch.items()}
    return (
        "Проанализируй тексты сообщений игроков за день. Для каждого user_id верни топ-5 самых частых слов.\n"
        "Правила:\n"
        "- Исключи предлоги, союзы, частицы и служебные слова.\n"
        "- Приведи слова к именительному падежу (лемма), нижний регистр.\n"
        "- Если ни одно слово не встречалось более 1 раза: no_word_repeated=true и top_words=[].\n"
        "- Иначе no_word_repeated=false и top_words: до 5 элементов {\"word\",\"count\"}, по убыванию count.\n"
        "- Ответ ТОЛЬКО валидный JSON без markdown:\n"
        '{"users":[{"user_id":123,"top_words":[{"word":"игра","count":5}],"no_word_repeated":false}]}\n'
        f"Данные:\n{json.dumps(payload, ensure_ascii=False)}"
    )


async def analyze_day_word_stats(
    log_by_user: dict[int, list[str]],
    *,
    timeout_sec: float = 60.0,
) -> dict[int, dict[str, Any]]:
    """RouterAI word stats with local fallback for missing/failed users."""
    if not log_by_user:
        return {}
    fallback = local_word_stats(log_by_user)
    if not has_text_llm_configured():
        return fallback

    merged: dict[int, dict[str, Any]] = {}
    for batch in _chunk_users(log_by_user):
        expected = set(batch.keys())
        try:
            text = await ai_generate(
                _build_prompt(batch),
                system=(
                    "Ты аналитик частоты слов. Отвечай только JSON. "
                    "Не цитируй сообщения целиком, не добавляй комментарии."
                ),
                preset=settings.ai_preset_gd,
                caller="gd-daily-words",
                timeout_sec=timeout_sec,
                max_tokens=1200,
                temperature=0.2,
                post_process_rhythm=False,
            )
            parsed = parse_word_stats_response(text, expected)
            for uid in expected:
                merged[uid] = parsed.get(uid) or fallback.get(uid) or {
                    "top_words": [],
                    "no_word_repeated": False,
                    "words_unavailable": True,
                }
        except Exception:
            logger.exception("GD daily word AI batch failed; using local fallback")
            for uid in expected:
                merged[uid] = fallback.get(uid) or {
                    "top_words": [],
                    "no_word_repeated": False,
                    "words_unavailable": True,
                }
    # Users with empty logs
    for uid in log_by_user:
        merged.setdefault(
            int(uid),
            fallback.get(int(uid))
            or {"top_words": [], "no_word_repeated": False, "words_unavailable": True},
        )
    return merged


def merge_word_stats_into_rows(
    rows: list[dict[str, Any]],
    word_stats: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach top_words / flags onto summary rows (in-place + return)."""
    for r in rows:
        uid = int(r.get("user_id") or 0)
        st = word_stats.get(uid)
        if not st:
            # No phantom text for this user
            if int(r.get("text_chars") or 0) <= 0:
                r["top_words"] = []
                r["no_word_repeated"] = False
                r["words_unavailable"] = False  # show "—" via formatter when no text
            else:
                r["top_words"] = []
                r["no_word_repeated"] = False
                r["words_unavailable"] = True
            continue
        r["top_words"] = list(st.get("top_words") or [])
        r["no_word_repeated"] = bool(st.get("no_word_repeated"))
        r["words_unavailable"] = bool(st.get("words_unavailable"))
    return rows
