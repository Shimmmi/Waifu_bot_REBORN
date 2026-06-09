"""Guild raid v2: AI narratives for weekly chronicle."""
from __future__ import annotations

import json
import logging
import random
import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from waifu_bot.core.config import settings
from waifu_bot.game.constants import RAID_V2_NARRATIVE_STYLE_RU, RAID_V2_SLOT_COUNT, RAID_V2_SLOT_HOURS
from waifu_bot.game.expedition_narrative_catalog import archetype_for_id
from waifu_bot.services.ai_narrative_rewrite import (
    _extract_openrouter_assistant_text,
    _openrouter_text_extra,
    escape_telegram_html,
    rhythm_rewrite_narrative,
)
from waifu_bot.services.gd_narrative_ai import format_gd_party_member_line
from waifu_bot.services.llm_client import has_llm_configured, post_chat_completions

logger = logging.getLogger(__name__)
_MSK = ZoneInfo("Europe/Moscow")

RAID_SYSTEM_PROMPT = (
    "Ты — рассказчик фэнтезийной RPG про гильдейские рейды-экспедиции. "
    "Пиши на русском, Telegram HTML (<b>, <i>), без markdown. "
    "Не упоминай числа механик и формулы. "
    f"{RAID_V2_NARRATIVE_STYLE_RU}"
)

_COMPOSE_INSTRUCTIONS = (
    "Собери утренний SUMMARY вчерашнего дня из готовых 4-часовых абзацев:\n"
    "- Каждый активный слот — отдельный абзац (можно слегка сгладить стиль).\n"
    "- Неактивные слоты объедини в ОДИН абзац про привал.\n"
    "- Если активности не было — один абзац про тихие сутки.\n"
    "- В конце добавь ОДИН абзац-переход к выбору тактики на сегодня (без перечисления вариантов).\n"
    "Не добавляй JSON, не перечисляй механики."
)

_TACTICS_JSON_INSTRUCTIONS = (
    "Верни ТОЛЬКО валидный JSON одной строкой, без пояснений и без HTML:\n"
    '{"tactics":[{"label":"...","risk":"low|medium|high","terrain_fit":["biome"]}, ...]}\n'
    "Нужно ровно 3–4 тактики в стиле приключения (короткие, до 90 символов каждая label)."
)


def _location_name(archetype_id: str | None) -> str:
    arch = archetype_for_id(archetype_id or "")
    return arch.name_ru if arch else (archetype_id or "неизвестные земли")


def pick_raid_adventure_goal(location_archetype_id: str, *, template_name: str | None = None) -> str:
    arch = archetype_for_id(location_archetype_id or "")
    hints = list(arch.narrative_hints) if arch and arch.narrative_hints else []
    hint = random.choice(hints) if hints else "добраться до цели и вернуться живыми"
    tier = (template_name or "").strip()
    if tier:
        return f"{hint} (рейд: {tier})"
    return hint


def _party_block(party: list[dict[str, Any]]) -> str:
    lines = [format_gd_party_member_line(p, for_start=True) for p in party]
    return "\n".join(lines) if lines else "- (пустой отряд)"


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _strip_leaked_json(text: str) -> str:
    """Remove trailing tactics JSON if it leaked into narrative."""
    raw = text or ""
    if '"tactics"' not in raw and not raw.rstrip().endswith("}"):
        return raw.strip()
    idx = raw.rfind('{"tactics"')
    if idx < 0:
        idx = raw.rfind("{")
    if idx >= 0:
        tail = raw[idx:].strip()
        try:
            json.loads(tail)
            return raw[:idx].strip()
        except json.JSONDecodeError:
            pass
    return raw.strip()


def _bold_proper_nouns(
    text: str,
    *,
    party: list[dict[str, Any]] | None = None,
    location: str | None = None,
    guild_name: str | None = None,
    guild_tag: str | None = None,
) -> str:
    if not text:
        return text
    names: list[str] = []
    for p in party or []:
        nm = str(p.get("name") or "").strip()
        if nm and len(nm) >= 2:
            names.append(nm)
    if location:
        names.append(location.strip())
    if guild_name:
        names.append(guild_name.strip())
    if guild_tag:
        names.append(f"[{guild_tag.strip()}]")
    names = sorted({n for n in names if n}, key=len, reverse=True)
    out = text
    for nm in names:
        pattern = re.compile(rf"(?<!<b>)(?<![\w>]){re.escape(nm)}(?![\w<])")
        out = pattern.sub(f"<b>{nm}</b>", out)
    return out


async def _call_llm_raw(user_prompt: str, *, caller: str, max_tokens: int = 900) -> str | None:
    if not has_llm_configured():
        return None
    payload = {
        "model": settings.openrouter_model,
        "max_tokens": max_tokens,
        "temperature": 0.85,
        "messages": [
            {"role": "system", "content": RAID_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        **_openrouter_text_extra(),
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await post_chat_completions(client, payload, caller=caller)
        if not r.is_success:
            logger.warning(
                "guild raid LLM HTTP %s caller=%s body=%s",
                r.status_code,
                caller,
                (r.text or "")[:400],
            )
            return None
        data = r.json()
        choices = data.get("choices") or []
        if not isinstance(choices, list) or not choices:
            return None
        return _extract_openrouter_assistant_text(choices[0]) or None
    except Exception:
        logger.exception("guild raid narrative LLM failed caller=%s", caller)
        return None


async def _finalize_narrative_html(
    raw: str | None,
    *,
    caller: str,
    party: list[dict[str, Any]] | None = None,
    location: str | None = None,
    guild_name: str | None = None,
    guild_tag: str | None = None,
    length_hint: str = "3–5 абзацев, Telegram HTML",
) -> str | None:
    if not raw:
        return None
    cleaned = _strip_leaked_json(_strip_html(raw))
    if not cleaned:
        return None
    text = escape_telegram_html(cleaned)
    rewritten = await rhythm_rewrite_narrative(
        text,
        caller=caller,
        length_hint=length_hint,
        preserve_html=True,
    )
    if not rewritten:
        return None
    return _bold_proper_nouns(
        rewritten,
        party=party,
        location=location,
        guild_name=guild_name,
        guild_tag=guild_tag,
    )


async def _call_llm(
    user_prompt: str,
    *,
    caller: str,
    max_tokens: int = 900,
    party: list[dict[str, Any]] | None = None,
    location: str | None = None,
    guild_name: str | None = None,
    guild_tag: str | None = None,
) -> str | None:
    raw = await _call_llm_raw(user_prompt, caller=caller, max_tokens=max_tokens)
    return await _finalize_narrative_html(
        raw,
        caller=caller,
        party=party,
        location=location,
        guild_name=guild_name,
        guild_tag=guild_tag,
    )


def _active_slots(slot_beats: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [sb for sb in (slot_beats or []) if not sb.get("rest")]


def _slot_summary(slot_beats: list[dict[str, Any]] | None) -> str:
    if not slot_beats:
        return "Активных слотов нет — весь день на привале."
    active_lines: list[str] = []
    rest_labels: list[str] = []
    for sb in slot_beats:
        label = sb.get("slot_label") or f"Слот {sb.get('slot_index', '?')}"
        if sb.get("rest"):
            rest_labels.append(str(label))
            continue
        actors = sb.get("active_players") or []
        previews = sb.get("previews") or []
        preview_bit = ""
        if previews:
            preview_bit = f" Фрагменты чата: {' | '.join(str(p)[:80] for p in previews[:5])}."
        actor_bit = ", ".join(str(a) for a in actors[:6]) if actors else "участники молчали"
        active_lines.append(f"- {label} [АКТИВЕН]: {actor_bit}.{preview_bit}")
    parts: list[str] = []
    if active_lines:
        parts.append("Активные 4-часовые слоты:")
        parts.extend(active_lines)
    if rest_labels:
        parts.append(f"Неактивные слоты (один абзац привала): {', '.join(rest_labels)}")
    elif not active_lines:
        parts.append("Активных слотов нет — весь день на привале (один абзац).")
    return "\n".join(parts)


def _slot_summaries_block(slot_summaries: list[dict[str, Any]]) -> str:
    if not slot_summaries:
        return "За сутки нет сохранённых 4-часовых summary."
    lines: list[str] = []
    for row in sorted(slot_summaries, key=lambda x: int(x.get("slot_index", 0))):
        label = row.get("slot_label") or f"Слот {row.get('slot_index', '?')}"
        html = _strip_html(str(row.get("summary_html") or ""))
        if html:
            lines.append(f"- {label}: {html[:500]}")
    return "\n".join(lines) if lines else "Summary пусты — тихие сутки."


def _build_slot_fallback_summary(
    *,
    slot_label: str,
    slot_beat: dict[str, Any],
    location: str,
) -> str:
    if slot_beat.get("rest"):
        return (
            f"В {slot_label} отряд в <b>{location}</b> дремал на привале — "
            "чат молчал, кроме редкого храпа."
        )
    actors = slot_beat.get("active_players") or []
    actor_bit = escape_telegram_html(", ".join(str(a) for a in actors[:6])) if actors else "отряд"
    previews = slot_beat.get("previews") or []
    if previews:
        flavor = escape_telegram_html(str(previews[0])[:120])
        return (
            f"В {escape_telegram_html(slot_label)} {actor_bit} оживили лагерь: "
            f"«{flavor}» — и снова в путь."
        )
    return (
        f"В {escape_telegram_html(slot_label)} {actor_bit} "
        f"поддерживали боевой дух у костра в <b>{location}</b>."
    )


def _build_compose_fallback_narrative(
    *,
    day_index: int,
    loc: str,
    slot_summaries: list[dict[str, Any]],
    company_vitality: int,
    story_progress: int,
) -> str:
    if not slot_summaries:
        return (
            f"<b>День {day_index}.</b> Отряд в <b>{loc}</b> провёл спокойные сутки на привале. "
            f"Выносливость {company_vitality}, прогресс {story_progress}."
        )
    parts = [f"<b>День {day_index}.</b> Хроника вчерашнего дня в <b>{loc}</b>:"]
    for row in sorted(slot_summaries, key=lambda x: int(x.get("slot_index", 0))):
        html = str(row.get("summary_html") or "").strip()
        if html:
            parts.append(html)
    parts.append(
        f"Утро. Отряд собирается выбрать тактику на новый день. "
        f"Выносливость {company_vitality}, прогресс {story_progress}."
    )
    return "\n\n".join(parts)


def _default_tactics(location_archetype_id: str) -> list[dict[str, Any]]:
    arch = archetype_for_id(location_archetype_id or "")
    biome = arch.biome_tag if arch else "forest"
    loc = arch.name_ru if arch else "локации"
    return [
        {"label": f"Осторожно ползти через {loc[:20]}", "risk": "low", "terrain_fit": [biome]},
        {"label": "Форсировать переход с песнями", "risk": "medium", "terrain_fit": [biome]},
        {"label": "Рискованный рейд вслепую", "risk": "high", "terrain_fit": [biome]},
    ]


def _parse_tactics_json(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        idx = text.find("{")
        if idx < 0:
            return []
        try:
            parsed = json.loads(text[idx:])
        except json.JSONDecodeError:
            logger.warning("guild raid tactics JSON parse failed")
            return []
    tactics: list[dict[str, Any]] = []
    for t in parsed.get("tactics") or []:
        if isinstance(t, dict) and t.get("label"):
            tactics.append(t)
    return tactics


async def generate_raid_slot_summary(
    *,
    guild_name: str,
    guild_tag: str,
    location_archetype_id: str,
    party: list[dict[str, Any]],
    slot_label: str,
    slot_beat: dict[str, Any],
) -> str:
    loc = _location_name(location_archetype_id)
    user = (
        f"4-часовой слот {slot_label}. Гильдия [{guild_tag}] «{guild_name}». Локация: {loc}.\n"
        f"Состав:\n{_party_block(party)}\n\n"
        f"Данные слота:\n{_slot_summary([slot_beat])}\n\n"
        "Напиши РОВНО ОДИН абзац summary этого 4-часового отрезка. "
        "Укажи, кто был активнее, настроение чата. Без JSON."
    )
    out = await _call_llm(
        user,
        caller="guild raid slot summary",
        max_tokens=400,
        party=party,
        location=loc,
        guild_name=guild_name,
        guild_tag=guild_tag,
    )
    if out:
        return out
    return _build_slot_fallback_summary(slot_label=slot_label, slot_beat=slot_beat, location=loc)


async def compose_raid_daily_narrative(
    *,
    guild_name: str,
    guild_tag: str,
    day_index: int,
    location_archetype_id: str,
    party: list[dict[str, Any]],
    slot_summaries: list[dict[str, Any]],
    company_vitality: int,
    story_progress: int,
    last_tactic: dict[str, Any] | None,
    last_resolve: dict[str, Any] | None,
    chronicle_summaries: list[str],
) -> str:
    loc = _location_name(location_archetype_id)
    prev = ""
    if last_tactic and last_resolve:
        tactic_label = last_tactic.get("label", "?")
        prev = (
            f"Вчера отряд выбрал тактику «{tactic_label}». "
            f"Последствия: выносливость {last_resolve.get('vitality_delta', '?')}, "
            f"прогресс +{last_resolve.get('progress_delta', '?')}."
        )
    hist = "\n".join(f"- {_strip_html(s)[:200]}" for s in chronicle_summaries[-3:])
    user = (
        f"День {day_index} из 7. Гильдия [{guild_tag}] «{guild_name}». Локация: {loc}.\n"
        f"Выносливость: {company_vitality}/100. Прогресс: {story_progress}/100.\n"
        f"{prev}\n\n"
        f"4-часовые summary за вчера:\n{_slot_summaries_block(slot_summaries)}\n\n"
        f"Недавняя хроника:\n{hist or '(нет)'}\n\n"
        f"Состав:\n{_party_block(party)}\n\n"
        f"{_COMPOSE_INSTRUCTIONS}"
    )
    out = await _call_llm(
        user,
        caller="guild raid daily compose",
        max_tokens=1200,
        party=party,
        location=loc,
        guild_name=guild_name,
        guild_tag=guild_tag,
    )
    if out:
        return _strip_leaked_json(out)
    return _build_compose_fallback_narrative(
        day_index=day_index,
        loc=loc,
        slot_summaries=slot_summaries,
        company_vitality=company_vitality,
        story_progress=story_progress,
    )


async def generate_raid_daily_tactics(
    *,
    guild_name: str,
    guild_tag: str,
    day_index: int,
    location_archetype_id: str,
    party: list[dict[str, Any]],
    narrative_preview: str,
    last_tactic: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    loc = _location_name(location_archetype_id)
    arch = archetype_for_id(location_archetype_id or "")
    biome = arch.biome_tag if arch else "forest"
    prev = ""
    if last_tactic:
        prev = f"Вчера выбрали: {last_tactic.get('label', '?')}."
    user = (
        f"День {day_index}. Гильдия [{guild_tag}] «{guild_name}». Локация: {loc} (biome: {biome}).\n"
        f"{prev}\n"
        f"Контекст утреннего summary:\n{_strip_html(narrative_preview)[:800]}\n\n"
        f"Состав:\n{_party_block(party)}\n\n"
        f"{_TACTICS_JSON_INSTRUCTIONS}"
    )
    raw = await _call_llm_raw(user, caller="guild raid daily tactics", max_tokens=600)
    tactics = _parse_tactics_json(raw)
    if len(tactics) < 3:
        return _default_tactics(location_archetype_id)[:4]
    return tactics[:4]


async def generate_raid_prologue(
    *,
    guild_name: str,
    guild_tag: str,
    location_archetype_id: str,
    party: list[dict[str, Any]],
    adventure_goal: str,
    template_name: str | None = None,
) -> str:
    loc = _location_name(location_archetype_id)
    goal = adventure_goal or pick_raid_adventure_goal(location_archetype_id, template_name=template_name)
    user = (
        f"Гильдия [{guild_tag}] «{guild_name}» отправляет отряд в недельную экспедицию.\n"
        f"Локация: {loc} (архетип {location_archetype_id}).\n"
        f"Цель приключения: {goal}.\n\n"
        f"Состав (имя, класс, раса, уровень):\n{_party_block(party)}\n\n"
        "Напиши PROLOGUE-брифинг: старт пути, атмосфера локации, цель, состав отряда. "
        "Без финального боя — только старт недельного приключения."
    )
    out = await _call_llm(
        user,
        caller="guild raid prologue",
        party=party,
        location=loc,
        guild_name=guild_name,
        guild_tag=guild_tag,
    )
    if out:
        return out
    names = ", ".join(p.get("name", "?") for p in party[:5])
    return (
        f"<b>Рейд начался.</b> Отряд гильдии <b>[{guild_tag}]</b> выдвигается в <b>{loc}</b>. "
        f"Цель: {escape_telegram_html(goal)}. "
        f"В походе: {escape_telegram_html(names)}."
    )


async def generate_raid_daily_narrative(
    *,
    guild_name: str,
    guild_tag: str,
    day_index: int,
    location_archetype_id: str,
    narrative_style_id: int,
    party: list[dict[str, Any]],
    slot_beats: list[dict[str, Any]],
    company_vitality: int,
    story_progress: int,
    last_tactic: dict[str, Any] | None,
    last_resolve: dict[str, Any] | None,
    chronicle_summaries: list[str],
) -> tuple[str, list[dict[str, Any]]]:
    """Legacy wrapper: compose from slot beats (used in tests). Returns (narrative, tactics)."""
    del narrative_style_id
    summaries = [
        {
            "slot_index": sb.get("slot_index", i),
            "slot_label": sb.get("slot_label"),
            "summary_html": _build_slot_fallback_summary(
                slot_label=str(sb.get("slot_label") or f"Слот {i}"),
                slot_beat=sb,
                location=_location_name(location_archetype_id),
            ),
        }
        for i, sb in enumerate(slot_beats or [])
        if not sb.get("rest")
    ]
    narrative = await compose_raid_daily_narrative(
        guild_name=guild_name,
        guild_tag=guild_tag,
        day_index=day_index,
        location_archetype_id=location_archetype_id,
        party=party,
        slot_summaries=summaries,
        company_vitality=company_vitality,
        story_progress=story_progress,
        last_tactic=last_tactic,
        last_resolve=last_resolve,
        chronicle_summaries=chronicle_summaries,
    )
    tactics = await generate_raid_daily_tactics(
        guild_name=guild_name,
        guild_tag=guild_tag,
        day_index=day_index,
        location_archetype_id=location_archetype_id,
        party=party,
        narrative_preview=narrative,
        last_tactic=last_tactic,
    )
    return narrative, tactics


async def generate_raid_defeat_epilogue(
    *,
    guild_name: str,
    guild_tag: str,
    location_archetype_id: str,
    party: list[dict[str, Any]],
    day_index: int,
) -> str:
    loc = _location_name(location_archetype_id)
    user = (
        f"Гильдия [{guild_tag}] «{guild_name}». Локация: {loc}. День {day_index}.\n"
        f"Отряд не выдержал экспедиции (выносливость 0).\n"
        f"Состав:\n{_party_block(party)}\n\n"
        "Напиши трагикомичный эпилог поражения."
    )
    out = await _call_llm(
        user,
        caller="guild raid defeat",
        party=party,
        location=loc,
        guild_name=guild_name,
        guild_tag=guild_tag,
    )
    return out or f"<b>Поражение.</b> Отряд [{guild_tag}] не выдержал похода в {loc}."


async def generate_raid_finale(
    *,
    guild_name: str,
    guild_tag: str,
    location_archetype_id: str,
    party: list[dict[str, Any]],
    outcome: str,
    story_progress: int,
    company_vitality: int,
) -> str:
    loc = _location_name(location_archetype_id)
    tone = {
        "victory": "триумф",
        "partial": "горько-sweet частичный успех",
        "failed": "срыв экспедиции",
    }.get(outcome, "финал")
    user = (
        f"Финал недельного рейда. Гильдия [{guild_tag}] «{guild_name}». Локация: {loc}.\n"
        f"Исход: {tone}. Прогресс {story_progress}/100, выносливость {company_vitality}.\n"
        f"Состав:\n{_party_block(party)}\n\n"
        "Напиши финальный эпилог недели."
    )
    out = await _call_llm(
        user,
        caller="guild raid finale",
        party=party,
        location=loc,
        guild_name=guild_name,
        guild_tag=guild_tag,
    )
    return out or f"<b>Финал рейда.</b> [{guild_tag}] завершила поход в {loc} ({tone})."


def pick_random_raid_location() -> str:
    from waifu_bot.game.expedition_narrative_catalog import pick_location_archetype

    return pick_location_archetype().id


def pick_random_raid_setting() -> tuple[str, int]:
    return pick_random_raid_location(), 0


def msk_slot_index_for_dt(dt: datetime) -> int:
    local = dt.astimezone(_MSK)
    return min(RAID_V2_SLOT_COUNT - 1, local.hour // RAID_V2_SLOT_HOURS)


def msk_slot_label(idx: int) -> str:
    start = idx * RAID_V2_SLOT_HOURS
    end = start + RAID_V2_SLOT_HOURS - 1
    return f"{start:02d}:00–{end:02d}:59 МСК"
