"""Guild raid v2: AI narratives for weekly chronicle."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from waifu_bot.game.constants import AI_NARRATIVE_GROTESQUE_HUMOR_RU
from waifu_bot.game.expedition_narrative_catalog import (
    EXPEDITION_LOCATION_ARCHETYPES,
    EXPEDITION_NARRATIVE_STYLES,
    STYLE_BY_ID,
    archetype_for_id,
)
from waifu_bot.services.ai_narrative_rewrite import escape_telegram_html, rhythm_rewrite_narrative
from waifu_bot.services.gd_narrative_ai import (
    format_gd_party_member_line,
    waifu_class_label_ru,
    waifu_race_label_ru,
)
from waifu_bot.services.llm_client import has_llm_configured, post_chat_completions

logger = logging.getLogger(__name__)

RAID_SYSTEM_PROMPT = (
    "Ты — рассказчик фэнтезийной RPG про гильдейские рейды-экспедиции. "
    "Пиши на русском, 3–5 абзацев, Telegram HTML (<b>, <i>), без markdown. "
    "Не упоминай числа механик и формулы. "
    f"{AI_NARRATIVE_GROTESQUE_HUMOR_RU}"
)


def _location_name(archetype_id: str | None) -> str:
    arch = archetype_for_id(archetype_id or "")
    return arch.name_ru if arch else (archetype_id or "неизвестные земли")


def _style_rules(style_id: int | None) -> str:
    st = STYLE_BY_ID.get(int(style_id or 0))
    return st.prompt_rules_ru if st else EXPEDITION_NARRATIVE_STYLES[0].prompt_rules_ru


def _party_block(party: list[dict[str, Any]]) -> str:
    lines = [format_gd_party_member_line(p, for_start=True) for p in party]
    return "\n".join(lines) if lines else "- (пустой отряд)"


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


async def _call_llm(user_prompt: str, *, caller: str, max_tokens: int = 900) -> str | None:
    if not has_llm_configured():
        return None
    try:
        raw = await post_chat_completions(
            messages=[
                {"role": "system", "content": RAID_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.85,
            caller=caller,
        )
        if not raw:
            return None
        text = escape_telegram_html(_strip_html(raw))
        return await rhythm_rewrite_narrative(text, caller=caller)
    except Exception:
        logger.exception("guild raid narrative LLM failed caller=%s", caller)
        return None


async def generate_raid_prologue(
    *,
    guild_name: str,
    guild_tag: str,
    location_archetype_id: str,
    narrative_style_id: int,
    party: list[dict[str, Any]],
) -> str:
    loc = _location_name(location_archetype_id)
    user = (
        f"Гильдия [{guild_tag}] «{guild_name}» отправляет отряд в недельную экспедицию.\n"
        f"Локация: {loc} (архетип {location_archetype_id}).\n"
        f"Стиль повествования: {_style_rules(narrative_style_id)}\n\n"
        f"Состав (основные вайфu):\n{_party_block(party)}\n\n"
        "Напиши PROLOGUE: начало пути, атмосфера локации, намёк на опасности впереди. "
        "Без финального боя — только старт недельного приключения."
    )
    out = await _call_llm(user, caller="guild raid prologue")
    if out:
        return out
    names = ", ".join(p.get("name", "?") for p in party[:5])
    return (
        f"<b>Рейд начался.</b> Отряд гильдии [{guild_tag}] выдвигается в <b>{loc}</b>. "
        f"В походе: {escape_telegram_html(names)}. Впереди — неделя странствий."
    )


def _slot_summary(slot_beats: list[dict[str, Any]] | None) -> str:
    if not slot_beats:
        return "За сутки отряд в основном отдыхал на привале."
    lines: list[str] = []
    for sb in slot_beats:
        label = sb.get("slot_label") or f"Слот {sb.get('slot_index', '?')}"
        if sb.get("rest"):
            lines.append(f"- {label}: привал, активности почти не было.")
            continue
        actors = sb.get("active_players") or []
        if actors:
            lines.append(f"- {label}: активность от {', '.join(str(a) for a in actors[:6])}.")
        else:
            lines.append(f"- {label}: тихо.")
    return "\n".join(lines)


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
    """Returns (narrative_html, tactic_options with mechanics filled by caller)."""
    loc = _location_name(location_archetype_id)
    prev = ""
    if last_tactic and last_resolve:
        prev = (
            f"Вчера отряд выбрал тактику «{last_tactic.get('label', '?')}». "
            f"Последствия: выносливость {last_resolve.get('vitality_delta', '?')}, "
            f"прогресс +{last_resolve.get('progress_delta', '?')}."
        )
    hist = "\n".join(f"- {s[:200]}" for s in chronicle_summaries[-3:])
    user = (
        f"День {day_index} из 7. Гильдия [{guild_tag}] «{guild_name}». Локация: {loc}.\n"
        f"Стиль: {_style_rules(narrative_style_id)}\n"
        f"Выносливость отряда: {company_vitality}/100. Прогресс экспедиции: {story_progress}/100.\n"
        f"{prev}\n\n"
        f"Слоты суток (МСК, по 3 часа):\n{_slot_summary(slot_beats)}\n\n"
        f"Недавняя хроника:\n{hist or '(нет)'}\n\n"
        f"Состав:\n{_party_block(party)}\n\n"
        "Напиши утренний SUMMARY вчерашнего дня. Если активности не было — опиши привал. "
        "Затем в конце ответа добавь блок JSON (одной строкой) с 3 вариантами тактики на сегодня:\n"
        '{"tactics":[{"label":"...","risk":"low|medium|high","terrain_fit":["swamp"]}, ...]}'
    )
    raw = await _call_llm(user, caller="guild raid daily", max_tokens=1200)
    tactics: list[dict[str, Any]] = []
    narrative = raw or ""
    if raw and "{" in raw:
        try:
            idx = raw.rfind("{")
            blob = raw[idx:]
            parsed = json.loads(blob)
            narrative = raw[:idx].strip()
            for t in parsed.get("tactics") or []:
                if isinstance(t, dict) and t.get("label"):
                    tactics.append(t)
        except json.JSONDecodeError:
            pass
    if not narrative:
        narrative = (
            f"<b>День {day_index}.</b> Отряд в <b>{loc}</b> "
            f"пережил спокойные сутки. Выносливость {company_vitality}, прогресс {story_progress}."
        )
    if len(tactics) < 3:
        arch = archetype_by_id(location_archetype_id or "")
        biome = arch.biome_tag if arch else "forest"
        tactics = [
            {"label": "Осторожный марш", "risk": "low", "terrain_fit": [biome]},
            {"label": "Форсировать переход", "risk": "medium", "terrain_fit": [biome]},
            {"label": "Рискованный рейд", "risk": "high", "terrain_fit": [biome]},
        ]
    return narrative, tactics[:4]


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
    out = await _call_llm(user, caller="guild raid defeat")
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
        "partial": "горько-сweet частичный успех",
        "failed": "срыв экспедиции",
    }.get(outcome, "финал")
    user = (
        f"Финал недельного рейда. Гильдия [{guild_tag}] «{guild_name}». Локация: {loc}.\n"
        f"Исход: {tone}. Прогресс {story_progress}/100, выносливость {company_vitality}.\n"
        f"Состав:\n{_party_block(party)}\n\n"
        "Напиши финальный эпилог недели."
    )
    out = await _call_llm(user, caller="guild raid finale")
    return out or f"<b>Финал рейда.</b> [{guild_tag}] завершила поход в {loc} ({tone})."


def pick_random_raid_setting() -> tuple[str, int]:
    from waifu_bot.game.expedition_narrative_catalog import pick_location_archetype, pick_narrative_style

    arch = pick_location_archetype()
    style = pick_narrative_style()
    return arch.id, int(style.id)
