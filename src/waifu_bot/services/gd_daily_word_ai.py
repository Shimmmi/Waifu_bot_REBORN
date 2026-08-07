"""End-of-day top-5 word stats via local Russian morphology (pymorphy3).

Consumes the phantom Redis log only; never persists raw message bodies.
LLM helpers below are kept for unit tests / legacy; analyze_day_word_stats
uses local counting only.
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from typing import Any

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

_morph: Any | None = None


def _get_morph() -> Any:
    """Lazy singleton MorphAnalyzer (expensive to construct)."""
    global _morph
    if _morph is None:
        import pymorphy3

        _morph = pymorphy3.MorphAnalyzer()
    return _morph


def _lemma(token: str) -> str:
    """Lowercase + ё→е + Russian lemma (surface form if morph fails)."""
    w = (token or "").lower().replace("ё", "е")
    if not w:
        return w
    # Latin / mixed tokens: morphology is RU-only; keep surface.
    if not any("а" <= ch <= "я" for ch in w):
        return w
    try:
        parsed = _get_morph().parse(w)
        if parsed:
            return str(parsed[0].normal_form).lower().replace("ё", "е")
    except Exception:
        logger.debug("pymorphy3 lemma failed for %r", w, exc_info=True)
    return w


def local_top_words_for_user(messages: list[str], *, top_n: int = 5) -> dict[str, Any]:
    """Frequency stats: lemmatized tokens, stopwords dropped. No profanity filter."""
    counts: Counter[str] = Counter()
    for msg in messages or []:
        for tok in _WORD_RE.findall(msg or ""):
            w = _lemma(tok)
            if not w or w in _STOPWORDS:
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
    """Parse RouterAI JSON into per-user word stats. Invalid/missing users omitted.

    Kept for unit tests / legacy; production analyze_day_word_stats is local-only.
    """
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
    """Legacy LLM prompt (unused by analyze_day_word_stats)."""
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
    """Local morph-aware word stats (no LLM). ``timeout_sec`` kept for call-site compat."""
    _ = timeout_sec
    if not log_by_user:
        return {}
    return local_word_stats(log_by_user)


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
