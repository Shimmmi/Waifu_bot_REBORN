"""ИИ-генерация текста событий экспедиции через OpenRouter (ТЗ)."""

from __future__ import annotations

import base64
import json
import logging
import random
import re
from io import BytesIO
from typing import Any, Optional, Sequence

import httpx
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.core.config import settings
from waifu_bot.db.models.dungeon import MonsterTemplate
from waifu_bot.db.models.skill import Skill, SkillType
from waifu_bot.game.constants import (
    AI_HIRE_MOMENT_MODERN_HUMOR_RU,
    AI_NARRATIVE_GROTESQUE_HUMOR_RU,
)
from waifu_bot.game.expedition_data import PERK_BY_ID
from waifu_bot.game.expedition_narrative_catalog import (
    ExpeditionNarrativeStyle,
    narrative_style_for_id,
    narrative_style_prompt_block,
)
from waifu_bot.services.ai_narrative_rewrite import rhythm_rewrite_narrative
from waifu_bot.services.ai_service import generate as ai_generate
from waifu_bot.services.llm_client import (
    IMAGE_MODALITY_ATTEMPTS,
    get_image_model,
    has_image_llm_configured,
    has_llm_configured,
    has_text_llm_configured,
    openrouter_headers_for_compat as _openrouter_headers,
    openrouter_url_for_compat as _openrouter_url,
    post_chat_completions,
)

logger = logging.getLogger(__name__)


async def _ai_text(
    prompt: str,
    *,
    caller: str,
    max_tokens: int = 512,
    temperature: float = 0.85,
    timeout_sec: float = 30.0,
    system: str | None = None,
) -> str | None:
    if not has_text_llm_configured():
        return None
    return await ai_generate(
        prompt,
        system=system,
        preset=settings.ai_preset_narrative,
        caller=caller,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout_sec=timeout_sec,
        post_process_rhythm=False,
    )


def _expedition_style_prompt_from_brief(brief: dict | None) -> str:
    if not isinstance(brief, dict):
        return ""
    style_id = brief.get("narrative_style_id")
    style = narrative_style_for_id(style_id)
    if style:
        return f" {narrative_style_prompt_block(style)}"
    name = str(brief.get("narrative_style_name") or "").strip()
    if name:
        return f" Стиль повествования «{name}» — сохраняй его на все эпизоды."
    return ""


def format_expedition_start_intro_telegram(
    *,
    title: str,
    intro_narrative: str,
    mode_name: str | None = None,
    archetype_name: str | None = None,
    squad_names: list[str] | None = None,
    style_name: str | None = None,
) -> str:
    t = str(title or "Экспедиция").strip()
    intro = str(intro_narrative or "").strip()
    if not intro:
        return ""
    style_bit = f" · {style_name}" if style_name else ""
    lines = [f"🗺 «{t}» · Брифинг{style_bit}", "", intro]
    meta: list[str] = []
    if mode_name and archetype_name:
        meta.append(f"{mode_name} · {archetype_name}")
    elif mode_name or archetype_name:
        meta.append(mode_name or archetype_name or "")
    if squad_names:
        meta.append(f"Отряд: {', '.join(squad_names[:5])}")
    if meta:
        lines.extend(["", "\n".join(x for x in meta if x)])
    return "\n".join(lines)


def _string_from_openrouter_content_part(block: object) -> str:
    """Текст из одного элемента message.content (строка или объект блока)."""
    if isinstance(block, str) and block.strip():
        return block.strip()
    if not isinstance(block, dict):
        return ""
    for key in ("text", "output_text", "content"):
        val = block.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        if isinstance(val, dict):
            for inner_key in ("value", "text", "content"):
                inner = val.get(inner_key)
                if isinstance(inner, str) and inner.strip():
                    return inner.strip()
    return ""


def _extract_openrouter_assistant_text(choice: object) -> str:
    """
    Достаёт текст ответа из choices[0] независимо от варианта схемы OpenRouter/OpenAI.
    У части моделей content — строка, у части — список блоков {type,text} или {type, text}.
    У reasoning/thinking-моделей (в т.ч. часть Gemini через OpenRouter) иногда пустой content,
    а видимый ответ — в message.reasoning; encrypted reasoning_details не используем.
    """
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
                piece = _string_from_openrouter_content_part(block)
                if piece:
                    parts.append(piece)
            if parts:
                return "\n".join(parts).strip()
        reasoning = msg.get("reasoning")
        if isinstance(reasoning, str) and reasoning.strip():
            return reasoning.strip()
    # legacy / альтернативные ответы
    t = choice.get("text")
    if isinstance(t, str) and t.strip():
        return t.strip()
    return ""


def _openrouter_text_extra() -> dict[str, object]:
    """Не отдавать reasoning-токены в ответе: экономия лимита и меньше пустого content у Gemini."""
    return {"reasoning": {"exclude": True}}


def _warn_if_empty_assistant(caller: str, choice: object, extracted: str) -> None:
    if extracted:
        return
    if not isinstance(choice, dict):
        return
    msg = choice.get("message")
    if not isinstance(msg, dict):
        logger.warning("OpenRouter %s: пустой текст, нет message в choice", caller)
        return
    raw = msg.get("content")
    logger.warning(
        "OpenRouter %s: пустой текст; message keys=%s content_type=%s",
        caller,
        list(msg.keys()),
        type(raw).__name__,
    )


async def refine_expedition_narrative_draft(
    draft: str,
    *,
    caller: str,
    length_hint: str,
) -> str:
    """Второй проход OpenRouter: rhythm-rewrite. При сбое — исходный draft."""
    return await rhythm_rewrite_narrative(
        draft,
        caller=caller,
        length_hint=length_hint,
        preserve_html=False,
    )


async def generate_expedition_narrative_brief(
    *,
    archetype_id: str,
    archetype_name: str,
    archetype_hints: list[str],
    mode_id: str,
    mode_name: str,
    mode_focus: str,
    mode_prompt_rules: str,
    affix_names: list[str],
    affix_hints: list[str],
    events_total: int,
    duration_minutes: int,
    squad_names: list[str],
    narrative_style: ExpeditionNarrativeStyle | None = None,
) -> Optional[dict]:
    """
    Генерирует JSON-бриф экспедиции при старте: название, сеттинг, план эпизодов.
    """
    if not has_text_llm_configured():
        return None

    payload = {
        "archetype": {
            "id": archetype_id,
            "name": archetype_name,
            "hints": archetype_hints[:6],
        },
        "mode": {
            "id": mode_id,
            "name": mode_name,
            "focus": mode_focus,
            "rules": mode_prompt_rules,
        },
        "affixes": [
            {"name": n, "hint": (affix_hints[i] if i < len(affix_hints) else "")}
            for i, n in enumerate(affix_names)
        ],
        "events_total": int(events_total),
        "duration_minutes": int(duration_minutes),
        "squad_names": squad_names[:5],
    }
    style_block = narrative_style_prompt_block(narrative_style) if narrative_style else ""
    prompt = (
        "Ты — сценарист коротких фэнтезийных экспедиций для RPG. "
        "Придумай уникальный сеттинг экспедиции по JSON-контексту. "
        f"{AI_NARRATIVE_GROTESQUE_HUMOR_RU} "
        f"{style_block} "
        "Не используй шаблон «подземелье с гоблинами», если архетип — город, клуб, арктика и т.п. "
        "Сеттинг должен соответствовать архетипу локации и режиму экспедиции. "
        f"event_beats — ровно {int(events_total)} коротких строк (одна на эпизод), "
        "логичная арка от начала до финала. "
        "event_beats задают атмосферу и сюжетный поворот эпизода; "
        "affixes в контексте — лишь примерный колорит старта, НЕ фиксируй всю экспедицию на них: "
        "конкретные препятствия каждого тика определятся позже, поэтому биты должны быть гибкими "
        "(место/настроение/цель), без жёсткой привязки к одному типу врагов. "
        "intro_narrative — 3–5 предложений: брифинг перед выходом, сбор отряда, что впереди; "
        "БЕЗ боевого действия, без урона, без «они уже сражаются» — это вступление, не первый эпизод. "
        "title — короткое кодовое имя миссии (2–5 слов), абсурдный гротескный юмор; "
        "примеры: «Операция гнилая картошка», «Проект мокрый носков», «Рейд на чайник судьбы». "
        "НЕ склеивай дословно mode.name, archetype.name и строки из affixes — "
        "используй контекст для смысла, но title должен звучать как уникальное прозвище операции.\n\n"
        "Ответь СТРОГО JSON без markdown:\n"
        '{"title":"...","setting_summary":"2-3 предложения","intro_narrative":"3-5 предложений брифинга",'
        '"key_elements":["..."],'
        f'"event_beats":["..."],"tone":"...","avoid_tropes":["..."]}}\n\n'
        f"Контекст: {json.dumps(payload, ensure_ascii=False)}"
    )

    try:
        text = await _ai_text(
            prompt,
            caller="expedition brief",
            max_tokens=650,
            temperature=0.88,
            timeout_sec=45.0,
        )
        if not text:
            return None
        parsed = _parse_narrative_brief_json(text)
        if parsed and narrative_style:
            parsed.setdefault("narrative_style_id", narrative_style.id)
            parsed.setdefault("narrative_style_name", narrative_style.name_ru)
        if parsed and not parsed.get("intro_narrative"):
            parsed["intro_narrative"] = parsed.get("setting_summary") or ""
        if parsed and len(parsed.get("event_beats") or []) != int(events_total):
            beats = list(parsed.get("event_beats") or [])
            while len(beats) < int(events_total):
                beats.append(f"Эпизод {len(beats) + 1}: развитие сюжета")
            parsed["event_beats"] = beats[: int(events_total)]
        if parsed:
            setting = str(parsed.get("setting_summary") or "").strip()
            if setting:
                parsed["setting_summary"] = await refine_expedition_narrative_draft(
                    setting,
                    caller="brief setting",
                    length_hint="2–3 предложения",
                )
            intro = str(parsed.get("intro_narrative") or "").strip()
            if intro:
                parsed["intro_narrative"] = await refine_expedition_narrative_draft(
                    intro,
                    caller="brief intro",
                    length_hint="3–5 предложений",
                )
        return parsed
    except Exception as e:
        logger.warning("OpenRouter expedition brief error: %s", e)
        return None


def _parse_narrative_brief_json(raw: str) -> Optional[dict]:
    raw = (raw or "").strip()
    if not raw:
        return None
    fence = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```\s*$", raw, re.IGNORECASE)
    if fence:
        raw = fence.group(1).strip()
    for candidate in (raw,):
        try:
            data = json.loads(candidate)
            if isinstance(data, dict) and data.get("title") and data.get("setting_summary"):
                intro = str(data.get("intro_narrative") or data.get("setting_summary") or "").strip()[:800]
                return {
                    "title": str(data["title"]).strip()[:120],
                    "setting_summary": str(data["setting_summary"]).strip()[:600],
                    "intro_narrative": intro,
                    "key_elements": [str(x).strip() for x in (data.get("key_elements") or []) if str(x).strip()][:8],
                    "event_beats": [str(x).strip() for x in (data.get("event_beats") or []) if str(x).strip()],
                    "tone": str(data.get("tone") or "fantasy-adventure").strip()[:64],
                    "avoid_tropes": [str(x).strip() for x in (data.get("avoid_tropes") or []) if str(x).strip()][:6],
                }
        except json.JSONDecodeError:
            pass
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict) and data.get("title"):
                return _parse_narrative_brief_json(json.dumps(data, ensure_ascii=False))
        except json.JSONDecodeError:
            pass
    return None


async def generate_expedition_tick_narrative(
    *,
    location: str,
    biome_tags: list[str],
    challenge_name: str,
    challenge_category: str,
    challenge_level: int,
    squad_snapshot: list[dict],
    outcome: str,
    event_num: int,
    total_events: int,
    is_final: bool,
    twist: dict | None,
    prev_summary: str,
    squad_hp_ratio: float = 0.0,
    expedition_context: dict | None = None,
) -> Optional[str]:
    """
    Короткий нарратив одного тика экспедиции v1.3 (2–4 предложения, RU).
    Контекст структурирован по ТЗ (биом, испытание, отряд, исход, твист).
    """
    if not has_text_llm_configured():
        return None

    ctx = {
        "location": location,
        "biome_tags": [t for t in biome_tags if t],
        "expedition": expedition_context or {},
        "challenge": {
            "name": challenge_name,
            "category": challenge_category,
            "level": challenge_level,
        },
        "squad": squad_snapshot,
        "outcome": outcome,
        "event_num": event_num,
        "total_events": total_events,
        "is_final": is_final,
        "twist": twist,
        "prev_summary": (prev_summary or "")[:500],
        "squad_hp_ratio": round(float(squad_hp_ratio), 3),
    }
    mode_rules = ""
    if expedition_context and expedition_context.get("mode_rules"):
        mode_rules = f" Режим экспедиции: {expedition_context['mode_rules']}"
    avoid = expedition_context.get("avoid_tropes") if expedition_context else None
    avoid_block = ""
    if avoid:
        avoid_block = f" Избегай клише: {', '.join(avoid[:4])}."
    beat_hint = ""
    if expedition_context and expedition_context.get("event_beat"):
        beat_hint = (
            " Поле expedition.event_beat — обязательный сюжетный поворот этого эпизода; "
            "не перескакивай к другим эпизодам."
        )
    threat_rules = (
        " Обязательно отрази в сцене угрозы ИМЕННО этого тика из expedition.threats.slot_affixes_ru "
        "и expedition.threats.uncovered_tags_ru (например «с пауками» → паутина, клыки) — "
        "это препятствия текущего эпизода, не всей экспедиции. "
        "Не называй механики и проценты — покажи через действие и атмосферу. "
        "Подготовка отряда (expedition.threats.squad_prepared): "
        "если true и outcome triumph — уверенное противодействие, наёмница с relevant_perk_names блеснёт; "
        "если false — отряд импровизирует, царапины и паника; при outcome triumph без контров — хрупкая удача, не мастерство; "
        "при struggle/survived_barely без контров — усиленное ощущение перегруза. "
        "Поле expedition.tick_pressure: high — больше хаоса, low — больше контроля."
    )
    style_block = _expedition_style_prompt_from_brief(expedition_context)
    intro_hint = ""
    if expedition_context and expedition_context.get("intro_narrative"):
        intro_hint = (
            " Это продолжение intro_narrative из брифинга — сохраняй тот же голос и стиль, "
            "не перескакивай к другому типу повествования."
        )
    prompt = (
        "Напиши короткое повествование (2–4 предложения, на русском) об одном эпизоде экспедиции в фэнтези-стиле. "
        f"{AI_NARRATIVE_GROTESQUE_HUMOR_RU} "
        f"{style_block}{intro_hint} "
        "Это эпизод номер event_num из total_events — обязательно другая сцена, другой момент конфликта, чем раньше. "
        "Не повторяй дословно и не копируй структуру предыдущего текста из prev_summary: придумай новое развитие. "
        "Поле squad_hp_ratio — доля суммарного здоровья отряда (0..1), без названия чисел: при низком значении больше угрозы, ран, усталости; при высоком — можно увереннее. "
        "Если is_final true — это последний эпизод перед возвращением; передай напряжение и состояние отряда, без спойлера итога всей экспедиции. "
        "Следуй контексту JSON; не перечисляй числа и механики вслух, покажи действие и атмосферу. "
        f"{mode_rules}{avoid_block}{beat_hint}{threat_rules} "
        "Исход outcome эпизода (не финал экспедиции): triumph — уверенный успех; struggle — с трудом; survived_barely — едва выстояли. "
        f"Контекст: {json.dumps(ctx, ensure_ascii=False)}"
    )

    try:
        text = await _ai_text(
            prompt,
            caller="expedition tick",
            max_tokens=320,
            temperature=0.82,
            timeout_sec=30.0,
        )
        if not text:
            return None
        return await refine_expedition_narrative_draft(
                text,
                caller="tick",
                length_hint="2–4 предложения",
            )
    except Exception as e:
        logger.warning("OpenRouter expedition tick error: %s", e)
        return None


async def generate_expedition_event(
    expedition_name: str,
    success: bool,
    duration_minutes: int,
    squad_names: list[str],
    reward_gold: int,
    reward_experience: int,
    *,
    narrative_brief: dict | None = None,
    mode_name: str | None = None,
    archetype_name: str | None = None,
    tick_summaries: list[str] | None = None,
    squad_prepared: bool | None = None,
) -> Optional[str]:
    """
    Генерирует итоговое описание экспедиции (3–5 предложений) через OpenRouter.
    Компонует эпизоды в связное повествование без цифр и наград.
    Возвращает None, если ключ не задан или запрос не удался.
    """
    if not has_text_llm_configured():
        return None

    outcome = "успешно завершили" if success else "не справились и вернулись с пустыми руками"
    names = ", ".join(squad_names[:5]) if squad_names else "отряд"
    context_parts: list[str] = []
    if narrative_brief:
        setting = (narrative_brief.get("setting_summary") or "")[:300]
        if setting:
            context_parts.append(f"Сеттинг: {setting}")
        intro = (narrative_brief.get("intro_narrative") or "")[:400]
        if intro:
            context_parts.append(f"Брифинг перед выходом: {intro}")
    if mode_name or archetype_name:
        context_parts.append(f"Режим: {mode_name or '—'}. Локация: {archetype_name or '—'}.")
    if squad_prepared is not None:
        prep = "отряд был подготовлен к угрозам" if squad_prepared else "отряд не имел нужных навыков"
        context_parts.append(f"Подготовка: {prep}.")
    episodes_block = ""
    if tick_summaries:
        lines = [s.strip() for s in tick_summaries if s and str(s).strip()]
        if lines:
            episodes_block = "\n".join(f"{i + 1}. {s[:300]}" for i, s in enumerate(lines))
    style_block = _expedition_style_prompt_from_brief(narrative_brief)
    context = "\n".join(context_parts)
    prompt = (
        f"Напиши связное итоговое повествование (3–5 предложений, на русском) о том, как прошла экспедиция. "
        f"{AI_NARRATIVE_GROTESQUE_HUMOR_RU} "
        f"{style_block} "
        f"Собери из эпизодов ниже единую историю приключений наёмниц ({names}). "
        f"Экспедиция «{expedition_name}»: отряд {outcome}. "
        f"Отрази настроение исхода, но НЕ упоминай время, минуты, золото, опыт, HP, проценты и любые числа — "
        f"награды показываются отдельно.\n"
    )
    if context:
        prompt += f"\nКонтекст:\n{context}\n"
    if episodes_block:
        prompt += f"\nЭпизоды экспедиции:\n{episodes_block}\n"
    prompt += "\nБез вступления, только текст итога."

    try:
        text = await _ai_text(
            prompt,
            caller="expedition event",
            max_tokens=280,
            temperature=0.7,
            timeout_sec=30.0,
        )
        if not text:
            return None
        return await refine_expedition_narrative_draft(
            text,
            caller="event",
            length_hint="3–5 предложений",
        )
    except Exception as e:
        logger.warning("expedition event error: %s", e)
        return None


def summarize_gate_log_fallback(
    gate_log: list[dict],
    *,
    outcome: str,
    expedition_name: str,
) -> str:
    """Лаконичный итог из gate_log без LLM."""
    outcome_ru = {
        "success": "успех",
        "partial_success": "частичный успех",
        "failure": "неудача",
    }.get(str(outcome or ""), "завершение")
    if not gate_log:
        return f"«{expedition_name}»: отряд вернулся ({outcome_ru})."
    lines = [str(e.get("text") or "").strip() for e in gate_log if e.get("text")]
    if not lines:
        return f"«{expedition_name}»: отряд вернулся ({outcome_ru})."
    return f"«{expedition_name}» ({outcome_ru}): " + "; ".join(lines[:8])


async def generate_gate_log_final_narrative(
    *,
    expedition_name: str,
    outcome: str,
    gate_log: list[dict],
) -> str | None:
    """Короткий итог (1–2 предложения) по gate_log; fallback — шаблон."""
    fallback = summarize_gate_log_fallback(
        gate_log, outcome=outcome, expedition_name=expedition_name
    )
    if not gate_log:
        return fallback
    if not has_text_llm_configured():
        return fallback
    entries_text = "\n".join(
        f"- {str(e.get('text') or '').strip()}" for e in gate_log[:12] if e.get("text")
    )
    if not entries_text.strip():
        return fallback
    outcome_ru = {
        "success": "успех",
        "partial_success": "частичный успех",
        "failure": "провал",
    }.get(str(outcome or ""), "завершение")
    prompt = (
        f"По пунктам лога экспедиции «{expedition_name}» напиши итог в 1–2 коротких предложениях на русском. "
        f"Исход похода: {outcome_ru}. Не упоминай золото, опыт, HP и проценты — только атмосферу и ключевые моменты.\n\n"
        f"Пункты лога:\n{entries_text}\n\nТолько текст итога, без списка."
    )
    try:
        text = await _ai_text(
            prompt,
            caller="expedition gate final",
            max_tokens=120,
            temperature=0.65,
            timeout_sec=25.0,
        )
        if text and text.strip():
            return text.strip()
    except Exception as e:
        logger.warning("gate log final narrative error: %s", e)
    return fallback


def _parse_name_bio_json(raw: str) -> Optional[tuple[str, str]]:
    """Извлекает name и bio из ответа ИИ. Защита от лишнего текста и markdown."""
    raw = (raw or "").strip()
    if not raw:
        return None
    # Снимаем обёртку ```json ... ``` если модель её добавила
    fence = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```\s*$", raw, re.IGNORECASE)
    if fence:
        raw = fence.group(1).strip()
    # Сначала пробуем распарсить целиком
    try:
        data = json.loads(raw)
        name = (data.get("name") or "").strip()
        bio = (data.get("bio") or "").strip()
        if name and bio:
            return (name, bio)
    except json.JSONDecodeError:
        pass
    # Вырезаем блок {...} на случай пояснений вокруг JSON
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        try:
            data = json.loads(match.group(0))
            name = (data.get("name") or "").strip()
            bio = (data.get("bio") or "").strip()
            if name and bio:
                return (name, bio)
        except json.JSONDecodeError:
            pass
    return None


async def generate_hire_waifu_name_and_bio(
    race_ru: str,
    class_ru: str,
    level: int,
    perk_names: list[str],
) -> Optional[tuple[str, str]]:
    """
    Генерирует имя и биографию наёмницы через OpenRouter.
    ИИ придумывает уникальное фэнтезийное женское имя (любой длины, с разнообразной фонетикой)
    по расе/классу и 2–3 предложения био. Возвращает (name, bio) или None при ошибке/недоступности.
    """
    if not has_text_llm_configured():
        return None

    skills_str = ", ".join(perk_names) if perk_names else "разнообразный опыт"

    prompt = f"""Ты — рассказчик в фэнтезийной RPG-игре про вайфу-наёмниц.
Придумай имя и биографию для наёмницы со следующими параметрами:
Раса: {race_ru}
Класс: {class_ru}
Уровень: {level}
Умения: {skills_str}

Требования к имени: уникальное фэнтезийное женское имя, подходящее под расу и класс (длина любая — от короткого до составного с прозвищем). Сильно варьируй фонетику, происхождение и культурный колорит между расами и наёмницами, чтобы имена не были похожи друг на друга. Не используй имена из популярных аниме и избегай заезженных шаблонов вроде «Аэль/Лира/Нэли/Кира/Сия/Мира».
Требования к биографии: 2–3 предложения, русский язык, живо и с характером, без механик и чисел. Упомяни умения через образы и действия.
{AI_NARRATIVE_GROTESQUE_HUMOR_RU} Имя и био — в том же духе.

Ответь СТРОГО в формате JSON без пояснений и markdown:
{{"name": "Имя", "bio": "Биография..."}}"""

    try:
        text = await _ai_text(
            prompt,
            caller="hire name+bio",
            max_tokens=300,
            temperature=1.0,
            timeout_sec=60.0,
        )
        parsed = _parse_name_bio_json(text or "")
        if not parsed and text:
            logger.warning(
                "hire name+bio: не удалось распарсить JSON, фрагмент ответа: %s",
                text[:240].replace("\n", " "),
            )
        return parsed
    except Exception as e:
        logger.warning("hire name+bio error: %s", e)
        return None


async def generate_shop_merchant_line(
    item_name: str,
    item_level: int,
    item_rarity: str,
    item_bonuses: str = "",
    context: str = "buy",
) -> Optional[str]:
    """
    Генерирует короткую реплику торговца для магазина (1–2 предложения, RU).
    context: buy — продаёшь со витрины; sell — покупаешь у странника; gamble — зовёшь на гембу.
    Использует ту же модель, что и генерация BIO наёмных вайфу (OPENROUTER_MODEL_HIRE или OPENROUTER_MODEL).
    """
    if not has_text_llm_configured():
        logger.warning("[shop merchant-line] Пропуск: не задан ROUTERAI_API_KEY")
        return None

    ctx = (context or "buy").strip().lower()
    if ctx not in ("buy", "sell", "gamble", "smith"):
        ctx = "buy"

    logger.info(
        "[shop merchant-line] Запрос AI preset=%s context=%s item=%s level=%s rarity=%s",
        settings.ai_preset_narrative,
        ctx,
        item_name,
        item_level,
        item_rarity,
    )
    bonuses_hint = ""
    if item_bonuses and item_bonuses.strip():
        bonuses_hint = f" Бонусы предмета (упомяни, если уместно): {item_bonuses.strip()}."

    if ctx == "gamble":
        prompt = (
            "Ты хитрый, но обаятельный барыга с мистической лавкой. "
            "1–2 предложения на русском: шепчешь страннику о скрытых сокровищах в мешках, лёгкий намёк на риск и награду. "
            "Обращение — «странник». Разрешены только теги <b>...</b>. Без markdown и без пояснений."
        )
    elif ctx == "smith":
        prompt = (
            "Ты старый кузнец в фэнтезийной кузнице. "
            "1–2 предложения на русском: расскажи о заточке предметов, шансе успеха и риске поломки после +7. "
            "Обращайся к клиенту как к «страннику». Разрешены только теги <b>...</b>. Без markdown и без пояснений."
        )
    elif ctx == "sell":
        prompt = (
            "Ты лавочник, который **покупает** б/у добычу у странников (не продаёшь). "
            f"1–2 предложения на русском: торгуйся шутливо, интересуйся товаром, зови показать вещи из сумки. "
            f"Конкретный лот на прилавке в уме: {item_name}, уровень {int(item_level)}, редкость {item_rarity}.{bonuses_hint} "
            "Обращайся к клиенту как к «страннику». Разрешены только теги <b>...</b> для названия вещи. Без markdown и без пояснений."
        )
    else:
        prompt = (
            "Ты торговец в фэнтезийном магазине. "
            f"1-2 предложения на русском, порекомендуй предмет со витрины: {item_name}, уровень {int(item_level)}, редкость {item_rarity}.{bonuses_hint} "
            "Обращайся к покупателю как \"странник\". "
            "Разрешены только теги <b>...</b> для названия предмета. Без markdown и без пояснений."
        )

    try:
        text = await _ai_text(
            prompt,
            caller="shop merchant-line",
            max_tokens=120,
            temperature=0.8,
            timeout_sec=45.0,
        )
        if not text:
            return None
        logger.info("[shop merchant-line] Успех, длина текста=%d", len(text))
        return text
    except Exception as e:
        logger.warning("[shop merchant-line] Ошибка запроса: %s", e, exc_info=True)
        return None


def _caravan_gk_truncate_text(text: Optional[str], max_len: int = 280) -> str:
    if not text:
        return ""
    s = str(text).strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def monster_template_dominant_trait_ru(mt: MonsterTemplate) -> str:
    """Одна человекочитаемая метка угрозы по кривым шаблона (без сравнения с героем)."""
    dpl = float(mt.dmg_per_level or 0)
    hpl = float(mt.hp_per_level or 0)
    bd = float(mt.base_difficulty or 0)
    tr = float(mt.tier or 0)
    candidates: list[tuple[float, str]] = [
        (dpl / 2.5, "в бою особенно опасен быстрым ростом урона с уровнем"),
        (hpl / 12.0, "пугает плотностью — много здоровья на уровень"),
        (bd / 40.0, "отличается высокой базовой сложностью шаблона"),
        (tr / 4.0, "считается серьёзной угрозой по рангу"),
    ]
    score, label = max(candidates, key=lambda x: x[0])
    if score <= 0:
        return "на дороге встречается как обычная угроза акта"
    return label


_CARAVAN_GK_SKILLS_LIMIT = 28
_CARAVAN_GK_SKILL_DESC_MAX = 280
_CARAVAN_GK_MONSTERS_FETCH_CAP = 160
_CARAVAN_GK_MONSTERS_SAMPLE = 18


async def build_caravan_driver_game_knowledge(
    session: AsyncSession,
    current_act: int,
) -> dict[str, Any]:
    """Активные навыки и выборка шаблонов монстров по акту для совета погонщицы."""
    act = int(current_act)
    skill_rows = (
        await session.execute(
            select(Skill.id, Skill.name, Skill.description)
            .where(Skill.skill_type == int(SkillType.ACTIVE))
            .order_by(Skill.id)
            .limit(_CARAVAN_GK_SKILLS_LIMIT)
        )
    ).all()
    skills: list[dict[str, Any]] = [
        {
            "id": row[0],
            "name": row[1],
            "description": _caravan_gk_truncate_text(row[2], _CARAVAN_GK_SKILL_DESC_MAX),
        }
        for row in skill_rows
    ]

    monster_q = await session.execute(
        select(MonsterTemplate).where(
            MonsterTemplate.act_min <= act,
            MonsterTemplate.act_max >= act,
        ).limit(_CARAVAN_GK_MONSTERS_FETCH_CAP)
    )
    pool = list(monster_q.scalars().all())
    random.shuffle(pool)
    pool = pool[:_CARAVAN_GK_MONSTERS_SAMPLE]
    monsters: list[dict[str, Any]] = [
        {
            "id": m.id,
            "name": m.name,
            "dominant_trait_ru": monster_template_dominant_trait_ru(m),
            "family": m.family,
            "tier": m.tier,
        }
        for m in pool
    ]
    return {"skills": skills, "monsters": monsters}


async def generate_caravan_driver_tip(
    *,
    current_act: int,
    max_act: int,
    gold: int,
    game_knowledge: Optional[dict[str, Any]] = None,
    narrative_context: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    """
    Короткий совет погонщицы каравана (2–4 предложения, RU), опирается на переданные игровые факты из БД.
    """
    if not has_text_llm_configured():
        logger.warning("[caravan driver-tip] Пропуск: не задан ROUTERAI_API_KEY")
        return None

    gk = game_knowledge if game_knowledge is not None else {"skills": [], "monsters": []}
    skills = gk.get("skills") or []
    monsters = gk.get("monsters") or []
    if not isinstance(skills, list):
        skills = []
    if not isinstance(monsters, list):
        monsters = []
    facts_payload = {"skills": skills, "monsters": monsters}
    facts_json = json.dumps(facts_payload, ensure_ascii=False)
    nar_block = ""
    if narrative_context:
        from waifu_bot.services.narrative import narrative_context_for_prompt_json

        nar_block = (
            "СЮЖЕТНЫЙ_КОНТЕКСТ (JSON, канон мира без спойлеров выше max_act):\n"
            f"{narrative_context_for_prompt_json(narrative_context)}\n\n"
        )

    prompt = (
        "Ты опытная погонщица каравана в фэнтезийном мире. Обращайся к собеседнику на «вы» как к страннику или командиру каравана. "
        f"Сейчас путь проходит через акт {int(current_act)} (доступно до акта {int(max_act)}); у странника примерно {int(gold)} монет золота — не перечисляй цифры сухим списком, можно намёк.\n\n"
        f"{nar_block}"
        "ИГРОВЫЕ_ФАКТЫ (JSON):\n"
        f"{facts_json}\n\n"
        "Правила ответа:\n"
        "- Дай 2–4 предложения, атмосферно, без списков и без markdown.\n"
        "- Если в JSON непустой массив skills или непустой массив monsters: опирайся на РОВНО ОДИН факт — либо один навык из skills (имя как в JSON, описание можно перефразировать), либо одного монстра из monsters (имя как в JSON, про угрозу используй только dominant_trait_ru и при желании family/tier из JSON). "
        "Не придумывай названий навыков или монстров, которых нет в JSON; не утверждай числовых формул или цифр, которых нет в переданных полях.\n"
        "- Если оба массива skills и monsters пусты: дай общий практический совет по дороге, осторожности и золоту в этом акте, без вымышленных имён навыков или чудовищ.\n"
        "- Если передан СЮЖЕТНЫЙ_КОНТЕКСТ: атмосфера и story_beats должны согласоваться с регионом; не раскрывай то, что в do_not_mention.\n"
        "- Если в JSON есть story_next_dungeon_name и story_focus_summary: кратко напомни этап пути (к цели или после этапа); "
        "не выдумывай названий подземелий — только story_next_dungeon_name из JSON.\n"
        "- Не выдавай точные коэффициенты баланса игры, кроме того что явно передано в JSON."
    )

    try:
        return await _ai_text(
            prompt,
            caller="caravan driver-tip",
            max_tokens=280,
            temperature=0.75,
            timeout_sec=45.0,
        )
    except Exception as e:
        logger.warning("[caravan driver-tip] Ошибка: %s", e)
        return None


async def generate_tavern_keeper_banter(
    *,
    current_act: int,
    max_act: int,
    gold: int,
    narrative_context: Optional[dict[str, Any]] = None,
    tavern_facts: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    """Короткая реплика тавернщика (слухи, быт), RU — OpenRouter."""
    if not has_text_llm_configured():
        logger.warning("[tavern keeper] Пропуск: не задан ROUTERAI_API_KEY")
        return None

    tf = tavern_facts if isinstance(tavern_facts, dict) else {}
    facts_json = json.dumps(tf, ensure_ascii=False)
    nar_block = ""
    if narrative_context:
        from waifu_bot.services.narrative import narrative_context_for_prompt_json

        nar_block = (
            "СЮЖЕТНЫЙ_КОНТЕКСТ (JSON):\n"
            f"{narrative_context_for_prompt_json(narrative_context)}\n\n"
        )

    prompt = (
        "Ты хозяин постоялого двора в фэнтезийном мире: грубоватый, но не злой. Обращайся на «вы». "
        f"Регион по акту {int(current_act)} (гость видел дороги до акта {int(max_act)}); в кошельке у гостя примерно {int(gold)} монет — без сухого перечисления цифр.\n\n"
        f"{nar_block}"
        "ФАКТЫ_О_ТАВЕРНЕ (JSON, может быть пусто):\n"
        f"{facts_json}\n\n"
        "Дай 2–4 предложения: слух у очага, быт, намёк на дорогу или найм — без markdown и списков. "
        "Не придумывай имён из игры, которых нет в JSON. Соблюдай do_not_mention из сюжетного контекста. "
        "Если в JSON есть story_next_dungeon_name и story_focus_summary — можно намекнуть на этап сюжета, "
        "не выдумывая других названий данжей."
    )

    try:
        return await _ai_text(
            prompt,
            caller="tavern keeper",
            max_tokens=300,
            temperature=0.78,
            timeout_sec=45.0,
        )
    except Exception as e:
        logger.warning("[tavern keeper] Ошибка: %s", e)
        return None


def fallback_main_waifu_bio(name: str, race_ru: str, class_ru: str) -> str:
    """Короткая биография без ИИ."""
    n = (name or "Героиня").strip() or "Героиня"
    r = (race_ru or "путница").strip()
    c = (class_ru or "искательница").strip()
    return f"{n} — {r} и {c} по призванию; дорога впереди длиннее, чем кажется."


async def generate_main_waifu_bio(
    *,
    name: str,
    race_ru: str,
    class_ru: str,
) -> Optional[str]:
    """2–4 предложения на русском для основной вайфу при создании (OpenRouter)."""
    if not has_text_llm_configured():
        logger.warning("[main waifu bio] Пропуск: не задан ROUTERAI_API_KEY")
        return None

    from waifu_bot.services.narrative import load_narrative_bible

    bible = load_narrative_bible()
    r1 = (bible.get("regions") or {}).get("1") or {}
    region_name = str(r1.get("name_ru") or "").strip() or "первый регион"
    region_mood = str(r1.get("mood") or "").strip()
    ab = bible.get("act_beats") or {}
    act1 = ab.get("1") or ab.get(1)
    hook = ""
    if isinstance(act1, list) and act1:
        hook = str(act1[0]).strip()

    prompt = (
        "Напиши краткую биографию героини для игры в жанре фэнтези (аниме-стилистика допустима). "
        "Только русский язык, 2–4 предложения, без списков и без markdown.\n\n"
        f"Имя: {name}\n"
        f"Раса: {race_ru}\n"
        f"Класс: {class_ru}\n"
        f"Стартовый регион (акт 1): {region_name}"
        + (f"; настроение: {region_mood}" if region_mood else "")
        + "\n"
    )
    if hook:
        prompt += f"Намёк на сюжет (не раскрывай будущие акты): {hook}\n"
    prompt += (
        "\nПравила: не упоминай концовку игры, империю целиком и «Грань» подробно; "
        "покажи мотивацию идти в приключение и лёгкую тень угрозы."
    )

    try:
        text = await _ai_text(
            prompt,
            caller="main waifu bio",
            max_tokens=400,
            temperature=0.72,
            timeout_sec=45.0,
        )
        return text.strip() if text else None
    except Exception as e:
        logger.warning("[main waifu bio] Ошибка: %s", e)
        return None


# Визуальные описания для промпта портрета (cursor_plan_7)
_CLASS_VISUAL = {
    "рыцарь": "female knight, armor, sword",
    "воин": "female warrior, armor, sword",
    "лучник": "female archer, forest ranger, bow and quiver",
    "маг": "female mage, magical staff, arcane robes",
    "ассасин": "female rogue, dark leather armor, daggers",
    "целительница": "female healer, white robes, glowing staff",
    "торговка": "female merchant, traveler coat, coin purse",
}
_RACE_VISUAL = {
    "человек": "human girl",
    "эльфийка": "elf girl, pointed ears, elegant",
    "зверолюдка": "kemonomimi girl, animal ears and tail",
    "ангел": "angel girl, white feathered wings, halo",
    "вампирша": "vampire girl, pale skin, red eyes, small fangs",
    "демоница": "demon girl, small curved horns, dark aura",
    "фея": "fairy girl, small iridescent wings, magical glow",
}

# English scene hints for hired waifu portrait (one random perk from waifu.perks)
_PERK_PORTRAIT_VISUAL_EN: dict[str, str] = {
    "gas_mask": "wearing a tactical gas mask half-raised, hazmat straps, cautious eyes",
    "diver": "wetsuit collar, snorkel mask on forehead, water droplets on skin",
    "fireproof": "heat shimmer aura, light soot smudges, calm near embers",
    "frostproof": "frosty breath mist, ice crystal sparkles in hair",
    "navigator": "holding a brass compass, rolled sea chart at belt",
    "desert_walker": "sun scarf, desert wind, sand dust on cloak",
    "gas_filter": "heavy-duty respirator filters visible, steampunk tubes",
    "snow_warrior": "fur-lined hood, snowflakes on lashes, ruddy cheeks",
    "acid_proof": "rubberized gear edges, protective goggles hanging on neck",
    "wind_walker": "scarf whipping in strong wind, dynamic hair motion",
    "elf_slayer": "battle-worn blade hilt, subtle elven rune trophy charm",
    "orc_hunter": "heavy crossbow strap, tribal war paint streak",
    "priest": "holy symbol pendant, soft golden light between hands",
    "demon_slayer": "blessed steel glint, faint holy seal pattern on gauntlet",
    "dragonslayer": "scorched scale fragment on pauldron, heroic upward gaze",
    "goblin_shaker": "mischievous grin, small bomb pouch at hip",
    "troll_slayer": "wooden club on shoulder, moss and mud stains",
    "vampire_hunter": "wooden stakes on bandolier, silver cross glint",
    "entomologist": "magnifying glass, pinned colorful beetle on lapel",
    "bat_hunter": "night sky cape, small bat charm earring",
    "mushroom_expert": "woven basket of glowing mushrooms, forest floor moss",
    "scout": "crouching among dense bushes, binoculars raised, stealthy focus",
    "archaeologist": "dusty gloves, ancient stone tablet fragment, fine brush",
    "swamp_walker": "knee-high waders, misty fen reeds behind",
    "spider_hunter": "torch glow, sticky web strands on sleeve",
    "chemist": "glass vials on belt, faint green vapor wisps",
    "magic_researcher": "floating arcane notes and tiny rune diagrams",
    "exorcist": "rosary wrapped around fist, faint ectoplasm mist",
    "mountain_engineer": "pickaxe handle visible, rock dust on cheeks",
    "anti_magnet": "copper coil jewelry, broken compass needle spinning",
    "curse_removal": "shattered chain motif, soft cleansing white aura",
    "anti_mage": "null-magic cuff on wrist, dispelling hand gesture",
    "spatial_mage": "slightly warped perspective echo around fingertips",
    "light_protection": "dark visor up on forehead, suppressed lens flare",
    "magic_resistance": "shimmering barrier-like skin sheen, defiant stance",
    "chronomancer": "floating clock gear fragments, frozen dust motes",
    "accelerator": "motion blur streaks, hair whipped to one side",
    "spatial_navigator": "bending corridor illusion grid reflected in eyes",
    "mana_shield": "crystalline mana shards orbiting one shoulder",
    "lucky": "four-leaf clover hair clip, golden lucky spark motes",
    "mental_shield": "psychic ripple halo blocking inward, focused brow",
    "strong_spirit": "iron-willed stance, inner fire reflected in pupils",
    "mental_clarity": "serene sharp gaze, single clean rim light",
    "sleepless": "stylized tired eyes, steam from mug at belt",
    "trusting": "warm open smile, hand extended in greeting",
    "photographic_memory": "faint glowing film-strip frames around temples",
    "calm": "meditative mudra, perfectly still hair despite wind",
    "optimist": "sunflower brooch, bright hopeful expression",
    "anger_control": "slow exhale pose, opening clenched fist gently",
    "passionate": "leaning forward energetically, lively spark in eyes",
}

_HIRE_PORTRAIT_POSE_EN: tuple[str, ...] = (
    "dynamic action-ready pose, slight torso twist",
    "three-quarter view turning toward camera",
    "slight crouch as if about to move, weight on front foot",
    "confident contrapposto stance, hand on hip",
    "looking over shoulder with alert expression",
    "low heroic angle, chin slightly lifted",
    "leaning on weapon or staff, relaxed but ready",
    "one knee raised on rock, wind in hair",
    "arms crossed with subtle smirk, strong silhouette",
    "mid-step freeze, cloak mid-swing for motion",
    "reaching toward viewer, engaging eye contact",
    "head tilted, playful asymmetrical composition",
)


_MAIN_WAIFU_RACE_VISUAL_EN: dict[int, str] = {
    1: "human girl",
    2: "elf girl, pointed ears, elegant",
    3: "kemonomimi girl, animal ears and tail",
    4: "angel girl, white feathered wings, halo",
    5: "vampire girl, pale skin, subtle fangs",
    6: "demon girl, small curved horns, dark aura",
    7: "fairy girl, small iridescent wings, magical glow",
}
_MAIN_WAIFU_CLASS_VISUAL_EN: dict[int, str] = {
    1: "female knight, sword",
    2: "female warrior, armor",
    3: "female archer, bow and quiver",
    4: "female mage, magical staff, arcane robes",
    5: "female rogue, dark leather, daggers",
    6: "female healer, white robes, glowing staff",
    7: "female merchant, traveler coat",
}
_MAIN_WAIFU_HAIR_EN: dict[str, str] = {
    "blonde": "blonde hair",
    "black": "black hair",
    "brown": "brown hair",
    "red": "red hair",
    "white": "white hair",
    "silver": "silver hair",
    "blue": "blue hair",
    "pink": "pink hair",
    "green": "green hair",
}
_MAIN_WAIFU_EYES_EN: dict[str, str] = {
    "red": "red eyes",
    "burgundy": "burgundy eyes",
    "pink": "pink eyes",
    "sky_blue": "sky blue eyes",
    "blue": "deep blue eyes",
    "turquoise": "turquoise eyes",
    "aquamarine": "aquamarine eyes",
    "green": "green eyes",
    "emerald": "emerald green eyes",
    "lime": "lime green eyes",
    "yellow": "yellow eyes",
    "amber": "amber eyes",
    "gold": "golden eyes",
    "orange": "orange eyes",
    "violet": "violet eyes",
    "gray": "gray eyes",
}
_MAIN_WAIFU_HAIRSTYLE_EN: dict[str, str] = {
    "short_bob": "short bob haircut",
    "spiky_short": "short spiky hair",
    "pixie": "pixie cut",
    "shaggy": "shaggy messy hair",
    "medium_straight": "medium length straight hair",
    "medium_wavy": "medium wavy hair",
    "medium_straight_bangs": "medium straight hair with bangs",
    "medium_wavy_2": "medium wavy hair style",
    "messy_medium": "messy medium length hair",
    "side_pony": "side ponytail",
    "twin_tails": "twin tails hairstyle",
    "long_pony": "long ponytail",
    "long_straight": "long straight hair",
    "long_curls": "long curly hair",
    "twin_tails_alt": "twin tails hairstyle variant",
    "side_braid": "side braid hairstyle",
    "space_buns": "space buns hairstyle",
    "hime_cut": "hime cut hairstyle",
}
_MAIN_WAIFU_EYE_SHAPE_EN: dict[str, str] = {
    "bright": "bright vivid eyes",
    "tsundere": "tsundere-style sharp but cute eyes",
    "cute": "cute large innocent eyes",
    "melancholy": "melancholic sad eyes",
    "serious": "serious stern eyes",
    "energetic": "energetic sparkling eyes",
    "mystic": "mystical glowing eyes",
    "gentle": "gentle soft eyes",
    "dormant_sleepy": "half-lidded sleepy eyes",
    "shocked": "wide shocked eyes",
    "playful": "playful mischievous eyes",
    "cold": "cold emotionless eyes",
    "confused": "confused uncertain eyes",
    "determination": "determined intense eyes",
    "yandere": "yandere obsessive eyes",
    "shyness": "shy averted eyes",
    "confidence": "confident sharp eyes",
    "tearful": "tearful glistening eyes",
    "joyful": "joyful bright eyes",
    "anger": "angry glaring eyes",
    "sleepy": "sleepy droopy eyes",
    "annoyed": "annoyed irritated eyes",
    "pouty": "pouty sulking eyes",
    "seductive": "seductive alluring eyes",
}
_MAIN_WAIFU_OUTFIT_EN: dict[str, str] = {
    "plate_armor": "full plate armor, fantasy knight",
    "leather_armor": "leather armor, ranger style",
    "chainmail": "chainmail armor under padding",
    "dress": "elegant fantasy dress",
    "robes": "flowing mage robes",
    "casual": "stylish casual modern clothes",
    "swimsuit": "one-piece swimsuit",
    "bikini": "bikini, beach-appropriate",
    "uniform": "smart uniform outfit",
    "kimono": "decorative kimono",
    "cloak": "hooded cloak over adventurer clothes",
}
_MAIN_WAIFU_ACC_MULTI_EN: dict[str, str] = {
    "none": "",
    "necklace": "visible necklace",
    "earrings": "earrings",
    "makeup_light": "light natural makeup",
    "makeup_bold": "bold makeup, eyeliner",
    "scars": "small facial scars",
    "freckles": "cute freckles",
    "glasses": "stylish glasses",
    "eyepatch": "eyepatch over one eye",
    "face_paint": "tribal face paint",
    "choker": "choker collar",
    "gloves": "fingerless gloves",
    "hat": "stylish hat",
    "hood": "hood up partially",
    "circlet": "ornate circlet on forehead",
    "hair_ribbon": "ribbon in hair",
}


def _b64_from_data_image_url(url: str) -> Optional[str]:
    if not isinstance(url, str) or not url.strip():
        return None
    m = re.match(r"^data:image/[\w.+-]+;base64,(.+)$", url.strip(), re.DOTALL)
    if m:
        return re.sub(r"\s+", "", m.group(1))
    return None


def _summarize_image_choice_for_log(choice: dict, *, limit: int = 1800) -> str:
    """Compact choice dump for parse-miss logs (no multi-MB base64 / reasoning blobs)."""

    def _short(obj: Any, depth: int = 0) -> Any:
        if isinstance(obj, dict):
            out: dict[str, Any] = {}
            for k, v in obj.items():
                if k in ("url", "b64_json", "signature", "data") and isinstance(v, str) and len(v) > 96:
                    out[k] = f"<str len={len(v)} prefix={v[:48]!r}>"
                elif k == "reasoning_details" and isinstance(v, list):
                    out[k] = f"<list len={len(v)}>"
                else:
                    out[k] = _short(v, depth + 1)
            return out
        if isinstance(obj, list):
            head = [_short(x, depth + 1) for x in obj[:2]]
            if len(obj) > 2:
                head.append(f"...+{len(obj) - 2}")
            return head
        if isinstance(obj, str) and len(obj) > 240:
            return f"<str len={len(obj)}>"
        return obj

    payload = {
        "finish_reason": choice.get("finish_reason"),
        "native_finish_reason": choice.get("native_finish_reason"),
        "choice_keys": list(choice.keys()),
        "message": _short(choice.get("message") if isinstance(choice.get("message"), dict) else {}),
    }
    return json.dumps(payload, ensure_ascii=False)[:limit]


def _log_image_parse_miss(
    tag: str,
    *,
    modalities: Sequence[str],
    choice: dict | None,
    usage: Any = None,
) -> None:
    choice_dict = choice if isinstance(choice, dict) else {}
    msg = choice_dict.get("message") if isinstance(choice_dict.get("message"), dict) else {}
    logger.info(
        "[%s] parse miss modalities=%s message_keys=%s finish_reason=%s usage=%s choice=%s",
        tag,
        modalities,
        list(msg.keys()) if isinstance(msg, dict) else [],
        choice_dict.get("finish_reason"),
        usage,
        _summarize_image_choice_for_log(choice_dict),
    )


def _image_url_block_url(block: object) -> str:
    if isinstance(block, dict):
        u = block.get("url")
        return str(u).strip() if u is not None else ""
    return ""


def _openrouter_image_part_url(part: object) -> str:
    """Поле image_url / imageUrl в ответе OpenRouter: объект {{url}} или сразу строка data:/https:."""
    if isinstance(part, str):
        return part.strip()
    if isinstance(part, dict):
        return _image_url_block_url(part)
    return ""


def _extract_openrouter_image_b64_sync(message: dict) -> Optional[str]:
    """Сырой base64 без префикса data: — только inline data URL."""
    images = message.get("images")
    if isinstance(images, list):
        for item in images:
            if not isinstance(item, dict):
                continue
            for key in ("image_url", "imageUrl"):
                u = _openrouter_image_part_url(item.get(key))
                if u:
                    b64 = _b64_from_data_image_url(u)
                    if b64:
                        return b64
            u = item.get("url")
            if isinstance(u, str):
                b64 = _b64_from_data_image_url(u)
                if b64:
                    return b64
    content = message.get("content")
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "image_url":
                continue
            for key in ("image_url", "imageUrl"):
                u = _openrouter_image_part_url(block.get(key))
                if u:
                    b64 = _b64_from_data_image_url(u)
                    if b64:
                        return b64
    if isinstance(content, str) and "base64," in content:
        m = re.search(r"data:image/[\w.+-]+;base64,([A-Za-z0-9+/=\s]+)", content)
        if m:
            return re.sub(r"\s+", "", m.group(1))
    return None


async def _fetch_http_image_as_b64(client: httpx.AsyncClient, url: str) -> Optional[str]:
    try:
        r = await client.get(url, follow_redirects=True, timeout=60.0)
        r.raise_for_status()
        return base64.standard_b64encode(r.content).decode("ascii")
    except Exception:
        logger.warning("[OPENROUTER IMAGE] fetch url failed prefix=%s", (url or "")[:96])
        return None


async def _extract_openrouter_image_b64(
    message: dict,
    client: httpx.AsyncClient,
) -> Optional[str]:
    sync = _extract_openrouter_image_b64_sync(message)
    if sync:
        return sync
    images = message.get("images")
    if isinstance(images, list):
        for item in images:
            if not isinstance(item, dict):
                continue
            for key in ("image_url", "imageUrl"):
                u = _openrouter_image_part_url(item.get(key))
                if u.startswith("http"):
                    got = await _fetch_http_image_as_b64(client, u)
                    if got:
                        return got
            u = item.get("url")
            if isinstance(u, str) and u.startswith("http"):
                got = await _fetch_http_image_as_b64(client, u)
                if got:
                    return got
    content = message.get("content")
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "image_url":
                continue
            for key in ("image_url", "imageUrl"):
                u = _openrouter_image_part_url(block.get(key))
                if u.startswith("http"):
                    got = await _fetch_http_image_as_b64(client, u)
                    if got:
                        return got
    return None


async def generate_main_waifu_portrait(
    race_id: int,
    class_id: int,
    hair_color: str,
    eye_colors: list[str],
    hairstyle: str,
    eye_shape: str,
    outfit: str,
    accessories: list[str],
) -> Optional[str]:
    """
    Портрет основной вайфу (превью при создании): RouterAI image API, anime 2:3.
    Возвращает только base64 без префикса data: или None.
    """
    if not has_image_llm_configured():
        logger.info("[MAIN OV IMAGE] Skip: no RouterAI API key")
        return None

    model = get_image_model()
    race_en = _MAIN_WAIFU_RACE_VISUAL_EN.get(int(race_id), "human girl")
    class_en = _MAIN_WAIFU_CLASS_VISUAL_EN.get(int(class_id), "female adventurer")
    hair = _MAIN_WAIFU_HAIR_EN.get(str(hair_color), "brown hair")
    ec_raw: list[str] = []
    for x in eye_colors or []:
        if x is None:
            continue
        s = str(x).strip()
        if s:
            ec_raw.append(s)
    ec_raw = ec_raw[:2]
    if len(ec_raw) >= 2:
        e1 = _MAIN_WAIFU_EYES_EN.get(ec_raw[0], "brown eyes")
        e2 = _MAIN_WAIFU_EYES_EN.get(ec_raw[1], "brown eyes")
        eyes = f"heterochromia, one eye {e1}, other eye {e2}"
    elif len(ec_raw) == 1:
        eyes = _MAIN_WAIFU_EYES_EN.get(ec_raw[0], "brown eyes")
    else:
        eyes = "brown eyes"
    hstyle = _MAIN_WAIFU_HAIRSTYLE_EN.get(str(hairstyle), "long hair")
    eye_sh = _MAIN_WAIFU_EYE_SHAPE_EN.get(str(eye_shape), "expressive eyes")
    outf = _MAIN_WAIFU_OUTFIT_EN.get(str(outfit), "fantasy outfit")
    acc_parts: list[str] = []
    if isinstance(accessories, list):
        for key in accessories:
            frag = _MAIN_WAIFU_ACC_MULTI_EN.get(str(key), "")
            if frag:
                acc_parts.append(frag)
    acc_joined = ", ".join(acc_parts)

    prompt = (
        f"anime style portrait, {race_en}, {class_en}, {hair}, {eyes}, {eye_sh}, {hstyle}, {outf}"
        + (f", {acc_joined}" if acc_joined else "")
        + ", fantasy RPG heroine, upper body, detailed face, soft lighting, "
        "high quality illustration, 1girl, safe for work"
    )
    logger.info(
        "[MAIN OV IMAGE] model=%s provider=routerai race=%s class=%s prompt_preview=%s",
        model,
        race_id,
        class_id,
        (prompt[:420] + "…") if len(prompt) > 420 else prompt,
    )

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            last_choice: dict = {}
            for modalities in IMAGE_MODALITY_ATTEMPTS:
                body = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "modalities": list(modalities),
                    "image_config": {
                        "aspect_ratio": "2:3",
                        "image_size": "1K",
                    },
                }
                r = await post_chat_completions(
                    client,
                    body,
                    caller="main ov image",
                    use_image_model=True,
                )
                if r.status_code == 401:
                    logger.error("[MAIN OV IMAGE] LLM 401")
                    return None
                if not r.is_success:
                    logger.error("[MAIN OV IMAGE] HTTP %s %s", r.status_code, (r.text or "")[:400])
                    return None

                data = r.json()
                choices = data.get("choices") or []
                if not isinstance(choices, list) or not choices:
                    logger.warning("[MAIN OV IMAGE] no choices modalities=%s", modalities)
                    continue
                first = choices[0]
                if not isinstance(first, dict):
                    continue
                last_choice = first
                message = first.get("message") or {}
                message = message if isinstance(message, dict) else {}
                b64_out = await _extract_openrouter_image_b64(message, client)
                if b64_out:
                    return b64_out
                _log_image_parse_miss(
                    "MAIN OV IMAGE",
                    modalities=modalities,
                    choice=first,
                    usage=data.get("usage"),
                )
            logger.warning(
                "[MAIN OV IMAGE] no base64 after attempts; last_choice=%s",
                _summarize_image_choice_for_log(last_choice),
            )
            return None
    except httpx.TimeoutException:
        logger.error("[MAIN OV IMAGE] timeout")
        return None
    except Exception as e:
        logger.exception("[MAIN OV IMAGE] %s", e)
        return None


_PAPERDOLL_POSES_NEUTRAL_EN: tuple[str, ...] = (
    "waist-up, relaxed heroic standing, arms at sides or one hand on hip, no weapons in hands",
    "waist-up, slight three-quarter view, friendly adventurer stance, empty hands visible",
    "waist-up, charismatic standing pose, slight lean, expressive but calm empty hands",
)

_PAPERDOLL_POSES_DUAL_WIELD_EN: tuple[str, ...] = (
    "waist-up, three-quarter view: right hand primary grip on main-hand weapon; left hand holds off-hand item "
    "(shield, orb, or dagger) — exactly two arms and two hands only",
    "waist-up, battle-ready stance: main weapon raised in primary hand; off-hand item held low at side — "
    "two arms, two hands, no extra limbs",
    "waist-up, dynamic guard pose: weapon forward in main hand, off-hand orb or shield presented — "
    "anatomically correct two arms only",
)

_PAPERDOLL_POSES_TWO_HAND_EN: tuple[str, ...] = (
    "waist-up, two-handed weapon grip with both hands on the same polearm or staff — exactly two arms on one weapon",
    "waist-up, heroic two-hand hold on great weapon, slight three-quarter angle, both hands visible on shaft",
)

_PAPERDOLL_POSES_ONE_HAND_EN: tuple[str, ...] = (
    "waist-up, main-hand weapon at side in single-hand grip; other hand empty on hip or relaxed — two arms only",
    "waist-up, confident one-hand weapon hold, off-hand free, slight three-quarter view",
)

_PAPERDOLL_POSES_ORB_CAST_EN: tuple[str, ...] = (
    "waist-up, casting pose: off-hand palm up presenting a magical orb; main hand free or resting on weapon — two arms",
    "waist-up, channeling stance: orb floating near off-hand, focused gaze, single orb in one hand only",
)

_PAPERDOLL_POSES_ARMOR_ONLY_EN: tuple[str, ...] = (
    "waist-up, relaxed standing in armor, hands empty and visible, no weapon draw pose",
    "waist-up, heroic showcase stance, arms relaxed at sides showing costume and jewelry",
)


def _paperdoll_slot_is_weapon(info: dict[str, str] | None) -> bool:
    if not info:
        return False
    st = str(info.get("slot_type") or "").lower()
    wt = str(info.get("weapon_type") or "").lower()
    if st in ("weapon_1h", "weapon_2h") or st.startswith("weapon"):
        return True
    if wt and wt not in ("orb",):
        return True
    return st == "offhand" and bool(wt)


def _paperdoll_slot_is_two_hand(info: dict[str, str] | None) -> bool:
    if not info:
        return False
    st = str(info.get("slot_type") or "").lower()
    wt = str(info.get("weapon_type") or "").lower()
    return st == "weapon_2h" or wt in ("two_hand", "2h", "bow", "staff", "staff_wand")


def _paperdoll_slot_is_orb(info: dict[str, str] | None) -> bool:
    if not info:
        return False
    wt = str(info.get("weapon_type") or "").lower()
    st = str(info.get("slot_type") or "").lower()
    return wt == "orb" or (st == "offhand" and wt == "orb")


def pick_paperdoll_pose_for_equipment(equipped_slots: dict[int, dict[str, str]]) -> str:
    """Pick an English pose hint from equipped slot types (1=main, 2=off, 3=costume, …)."""
    main = equipped_slots.get(1)
    off = equipped_slots.get(2)
    has_main = _paperdoll_slot_is_weapon(main)
    has_off = bool(off) and (
        _paperdoll_slot_is_weapon(off)
        or str(off.get("slot_type") or "").lower() == "offhand"
    )

    if has_main and has_off:
        if _paperdoll_slot_is_orb(off) or _paperdoll_slot_is_orb(main):
            return random.choice(_PAPERDOLL_POSES_ORB_CAST_EN)
        return random.choice(_PAPERDOLL_POSES_DUAL_WIELD_EN)

    if has_main and _paperdoll_slot_is_two_hand(main):
        return random.choice(_PAPERDOLL_POSES_TWO_HAND_EN)

    if has_main:
        return random.choice(_PAPERDOLL_POSES_ONE_HAND_EN)

    if has_off and _paperdoll_slot_is_orb(off):
        return random.choice(_PAPERDOLL_POSES_ORB_CAST_EN)

    if equipped_slots:
        return random.choice(_PAPERDOLL_POSES_ARMOR_ONLY_EN)

    return random.choice(_PAPERDOLL_POSES_NEUTRAL_EN)


# Waist-up portraits usually show hands below ~40% height; crop higher to keep arms out of the reference.
_PAPERDOLL_IDENTITY_CROP_HEIGHT_RATIO = 0.38
_PAPERDOLL_IDENTITY_CROP_ASPECT = 3 / 4  # portrait 3:4 (width:height)
_PAPERDOLL_GENERATION_MAX_ATTEMPTS = 2


def _is_portrait_image_b64(b64: str) -> bool:
    """True when decoded image is taller than wide."""
    try:
        raw = base64.b64decode(str(b64 or "").strip(), validate=False)
        if not raw:
            return False
        img = Image.open(BytesIO(raw))
        w, h = img.size
        return w < h
    except Exception:
        return False


def _crop_portrait_identity_reference_for_paperdoll(raw_b64: str) -> tuple[str, str] | None:
    """
    Tight head/upper-neck crop so multimodal models cannot copy arm poses from the full portrait.
    Returns (base64, mime) as PNG, or None on failure (caller keeps full portrait).
    """
    try:
        raw = base64.b64decode(str(raw_b64 or "").strip(), validate=False)
    except Exception:
        return None
    if not raw:
        return None
    try:
        img = Image.open(BytesIO(raw))
        img.load()
    except Exception:
        logger.warning("[MAIN OV PAPERDOLL] identity crop: cannot decode portrait")
        return None

    w, h = img.size
    if w < 16 or h < 16:
        return None

    crop_h = max(48, min(h, int(h * _PAPERDOLL_IDENTITY_CROP_HEIGHT_RATIO)))
    crop_w = max(16, min(w, int(crop_h * _PAPERDOLL_IDENTITY_CROP_ASPECT)))
    left = max(0, (w - crop_w) // 2)
    right = left + crop_w
    box = (left, 0, right, crop_h)
    try:
        cropped = img.crop(box)
    except Exception:
        logger.warning("[MAIN OV PAPERDOLL] identity crop: crop failed")
        return None

    if cropped.mode in ("RGBA", "LA", "P"):
        background = Image.new("RGB", cropped.size, (245, 240, 230))
        if cropped.mode == "P":
            cropped = cropped.convert("RGBA")
        if cropped.mode in ("RGBA", "LA"):
            background.paste(cropped, mask=cropped.split()[-1])
            cropped = background
        else:
            cropped = cropped.convert("RGB")
    elif cropped.mode != "RGB":
        cropped = cropped.convert("RGB")

    buf = BytesIO()
    cropped.save(buf, format="PNG", optimize=True)
    out = buf.getvalue()
    if not out:
        return None
    cw, ch = cropped.size
    logger.info(
        "[MAIN OV PAPERDOLL] identity crop %dx%d -> %dx%d (ratio=%.2f)",
        w,
        h,
        cw,
        ch,
        cw / ch if ch else 0.0,
    )
    return base64.b64encode(out).decode("ascii"), "image/png"


def _paperdoll_background_for_avg_tier(avg_tier: float) -> str:
    t = float(avg_tier or 1.0)
    if t >= 9.0:
        return (
            "Background: legendary divine atmosphere — rich deep gradient (royal violet to gold), "
            "intense golden god-rays, radiant halo glow behind the character, sparkling particles and arcane energy wisps, "
            "premium loot aura; no scenery, no text."
        )
    if t >= 7.0:
        return (
            "Background: epic high-tier fantasy — dramatic purple-blue gradient with bright rim light, "
            "floating sparkles, soft energy wisps and subtle lens flare; heroic showcase feel; no scenery, no text."
        )
    if t >= 5.0:
        return (
            "Background: rare gear atmosphere — warm amber and teal gradient, magical particle motes, "
            "soft rim glow around the silhouette, light VFX sparkles; no scenery, no text."
        )
    if t >= 3.0:
        return (
            "Background: uncommon quality — soft vertical gradient (warm cream to pale gold), "
            "gentle warm aura and faint glow behind shoulders; no scenery, no text."
        )
    return (
        "Background: solid or very soft vertical gradient light beige (#f5f0e6 to #ebe4d6), warm parchment tone, "
        "minimal effects; no scenery, no patterns, no text — must harmonize with a soft UI paperdoll panel."
    )


async def generate_main_waifu_paperdoll_from_portrait(
    *,
    portrait_b64: str,
    portrait_mime: str,
    race_id: int,
    class_id: int,
    equipment_prompt_en: str | None = None,
    equipment_references: list[tuple[str, str]] | None = None,
    avg_equipment_tier: float = 1.0,
    pose_hint_en: str | None = None,
) -> Optional[str]:
    """
    2D JRPG-style paperdoll (waist-up) from existing portrait: multimodal request to ROUTERAI_MODEL_IMAGE.
    Returns raw base64 or None.
    """
    if not has_image_llm_configured():
        logger.info("[MAIN OV PAPERDOLL] Skip: no RouterAI API key")
        return None

    raw_b64 = str(portrait_b64 or "").strip()
    if not raw_b64:
        logger.info("[MAIN OV PAPERDOLL] Skip: empty portrait")
        return None

    mime = (portrait_mime or "image/png").strip() or "image/png"
    if ";" in mime or "/" not in mime:
        mime = "image/png"
    identity_b64 = raw_b64
    cropped = _crop_portrait_identity_reference_for_paperdoll(raw_b64)
    identity_cropped = cropped is not None
    if cropped:
        identity_b64, mime = cropped
    data_url = f"data:{mime};base64,{identity_b64}"

    model = get_image_model()
    race_en = _MAIN_WAIFU_RACE_VISUAL_EN.get(int(race_id), "human girl")
    class_en = _MAIN_WAIFU_CLASS_VISUAL_EN.get(int(class_id), "female adventurer")
    raw_eq = str(equipment_prompt_en or "").strip()
    equip_extra = "\n\n" + raw_eq if raw_eq else ""
    pose_en = str(pose_hint_en or "").strip() or random.choice(_PAPERDOLL_POSES_NEUTRAL_EN)
    bg_en = _paperdoll_background_for_avg_tier(avg_equipment_tier)
    gear_ref_note = ""
    refs = equipment_references or []
    if refs:
        gear_ref_note = (
            f"\nAttached after the identity portrait: {len(refs)} reference image(s) of equipped gear — "
            "integrate each item's design onto the character in the matching slot."
        )
    identity_ref_note = (
        "The attached identity image is a tight head-and-upper-neck crop only — it intentionally contains NO arms, "
        "hands, torso below the collarbone, or full-body pose. Do not hallucinate extra arms from any other source."
        if identity_cropped
        else (
            "The attached identity image must be used for face and hair only — ignore any visible arms or hands in it "
            "and draw a completely new body pose."
        )
    )
    prompt = (
        "Generate a single JRPG-style 2D full-color illustration of a fantasy heroine with the SAME identity as the "
        "attached identity reference, but in a completely NEW full waist-up pose drawn from scratch."
        f"\n{identity_ref_note}"
        "\nIdentity (copy from identity reference ONLY): same face, facial features, eye colors (including heterochromia), "
        "nose, mouth shape, hairstyle, hair color, skin tone, horns, ears, and general body type. Do not redesign the face."
        "\nDraw ALL arms, hands, and fingers ONLY from the Pose requirement below — never copy limb positions from any reference."
        "\nAnatomy (mandatory): exactly two arms and two hands total in the final image; anatomically correct; "
        "each hand holds at most one item; no duplicate arms, no merged limbs, no third arm, no extra floating hands."
        f"\nPose (mandatory — sole source for limb layout): {pose_en}"
        f"\nCharacter flavor: {race_en}, {class_en}."
        f"{equip_extra}"
        f"{gear_ref_note}"
        "\nArt style: soft cel-shading, clean line art, not photorealistic, not 3D render, fantasy JRPG character art. "
        "Safe for work, 1girl."
        "\nCanvas: vertical portrait orientation only — image must be taller than wide (3:4 aspect ratio)."
        f"\n{bg_en}"
    )
    logger.info(
        "[MAIN OV PAPERDOLL] model=%s race=%s class=%s equip_chars=%s refs=%s avg_tier=%.2f pose=%s",
        model,
        race_id,
        class_id,
        len(raw_eq),
        len(refs),
        float(avg_equipment_tier or 1.0),
        pose_en[:64],
    )

    user_content: list[dict[str, Any]] = [
        {"type": "text", "text": prompt},
        {
            "type": "text",
            "text": (
                "Identity reference — tight head/upper-neck crop ONLY (no arms or hands visible). "
                "Copy face, hair, horns, ears, eye colors; IGNORE any limb pose hints:"
            ),
        },
        {"type": "image_url", "image_url": {"url": data_url}},
    ]
    for slot_label, ref_url in refs:
        label = str(slot_label or "Gear").strip() or "Gear"
        url = str(ref_url or "").strip()
        if not url:
            continue
        user_content.append(
            {"type": "text", "text": f"Reference gear image for {label} — match this item on the character:"}
        )
        user_content.append({"type": "image_url", "image_url": {"url": url}})

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            last_message: dict = {}
            for gen_attempt in range(_PAPERDOLL_GENERATION_MAX_ATTEMPTS):
                landscape_retry = False
                for modalities in IMAGE_MODALITY_ATTEMPTS:
                    body = {
                        "model": model,
                        "messages": [{"role": "user", "content": user_content}],
                        "modalities": list(modalities),
                        "image_config": {
                            "aspect_ratio": "3:4",
                            "image_size": "1K",
                        },
                    }
                    r = await post_chat_completions(
                        client,
                        body,
                        caller="main ov paperdoll",
                        use_image_model=True,
                    )
                    if r.status_code == 401:
                        logger.error("[MAIN OV PAPERDOLL] LLM 401")
                        return None
                    if not r.is_success:
                        logger.error("[MAIN OV PAPERDOLL] HTTP %s %s", r.status_code, (r.text or "")[:400])
                        return None

                    data = r.json()
                    choices = data.get("choices") or []
                    if not isinstance(choices, list) or not choices:
                        logger.warning("[MAIN OV PAPERDOLL] no choices modalities=%s", modalities)
                        continue
                    first = choices[0]
                    if not isinstance(first, dict):
                        continue
                    message = first.get("message") or {}
                    last_message = message if isinstance(message, dict) else {}
                    b64_out = await _extract_openrouter_image_b64(last_message, client)
                    if not b64_out:
                        logger.info(
                            "[MAIN OV PAPERDOLL] no image in message modalities=%s keys=%s",
                            modalities,
                            list(last_message.keys()),
                        )
                        continue
                    if _is_portrait_image_b64(b64_out):
                        return b64_out
                    try:
                        raw = base64.b64decode(b64_out.strip(), validate=False)
                        img = Image.open(BytesIO(raw))
                        iw, ih = img.size
                    except Exception:
                        iw, ih = 0, 0
                    logger.warning(
                        "[MAIN OV PAPERDOLL] landscape output %dx%d gen_attempt=%s modalities=%s — retry",
                        iw,
                        ih,
                        gen_attempt + 1,
                        modalities,
                    )
                    landscape_retry = True
                    break
                if not landscape_retry:
                    break
            logger.warning(
                "[MAIN OV PAPERDOLL] no portrait base64 after attempts; last_message=%s",
                json.dumps(last_message, ensure_ascii=False)[:700],
            )
            return None
    except httpx.TimeoutException:
        logger.error("[MAIN OV PAPERDOLL] timeout")
        return None
    except Exception as e:
        logger.exception("[MAIN OV PAPERDOLL] %s", e)
        return None


_HIRE_PERK_MOMENT_MAX_CHARS = 200


def _sanitize_hire_perk_moment_ru(raw: str) -> str:
    """Одно предложение, без лишних пробелов, не длиннее лимита."""
    t = (raw or "").strip()
    t = re.sub(r"[\r\n]+", " ", t)
    t = re.sub(r"\s+", " ", t)
    for sep in (".", "!", "?", "…"):
        pos = t.find(sep)
        if pos != -1:
            t = t[: pos + 1].strip()
            break
    if len(t) > _HIRE_PERK_MOMENT_MAX_CHARS:
        t = t[:_HIRE_PERK_MOMENT_MAX_CHARS].rstrip()
    return t


async def generate_hire_waifu_perk_moment_ru(
    *,
    perk_id: str,
    perk_name_ru: str,
    name: str,
    race_ru: str,
    class_ru: str,
    bio: str,
) -> Optional[str]:
    """
    Одно короткое предложение на русском: визуальный момент для аниме-портрета, связанный с перком.
    """
    if not has_text_llm_configured():
        return None

    bio_short = (bio or "").strip()
    if len(bio_short) > 400:
        bio_short = bio_short[:400].rstrip() + "…"

    user_prompt = f"""Персонаж: наёмница «{name}», раса: {race_ru}, класс: {class_ru}.
Умение (перк) для сцены: «{perk_name_ru}» (внутренний id: {perk_id}).
Краткая био (контекст, не цитируй дословно): {bio_short or "нет"}

Напиши РОВНО ОДНО короткое предложение на русском языке — конкретный визуальный момент для аниме-портрета верхней части тела: что она делает, что видно вокруг, настроение. Сцена должна буквально и с юмором обыгрывать суть умения «{perk_name_ru}».
{AI_HIRE_MOMENT_MODERN_HUMOR_RU}
Без markdown, без кавычек, без списков, без чисел и игровых механик, без обращения к зрителю. Только текст предложения."""

    try:
        text = await _ai_text(
            user_prompt,
            caller="hire portrait moment",
            max_tokens=120,
            temperature=1.05,
            timeout_sec=40.0,
        )
        if not text:
            return None
        out = _sanitize_hire_perk_moment_ru(text)
        return out or None
    except Exception as e:
        logger.warning("[HIRE PORTRAIT MOMENT] error: %s", e)
        return None


async def generate_hire_waifu_image(
    race_ru: str,
    class_ru: str,
    bio: str,
    name: str = "",
    perk_ids: Sequence[str] | None = None,
) -> Optional[str]:
    """
    Генерирует портрет наёмницы через RouterAI image API (cursor_plan_7).
    Случайный перк из perk_ids: статический EN-фрагмент + при успехе ИИ — одно RU-предложение
    момента вместо случайной позы; иначе поза из пула.
    Возвращает base64-строку изображения или None при ошибке.
    Парсинг: message.images[0].image_url.url, не content.
    """
    if not has_image_llm_configured():
        logger.info("[IMAGE GEN] Skip: no RouterAI API key")
        return None

    model = get_image_model()
    race_key = (race_ru or "человек").strip().lower()
    class_key = (class_ru or "маг").strip().lower()
    race_visual = _RACE_VISUAL.get(race_key, "human girl")
    class_visual = _CLASS_VISUAL.get(class_key, "adventurer")

    candidates = [str(p).strip() for p in (perk_ids or ()) if str(p).strip()]
    chosen_perk_id: str | None = None
    perk_snippet = ""
    if candidates:
        chosen_perk_id = random.choice(candidates)
        perk_snippet = (_PERK_PORTRAIT_VISUAL_EN.get(chosen_perk_id) or "").strip()

    pose_snippet = random.choice(_HIRE_PORTRAIT_POSE_EN)
    if chosen_perk_id:
        perk_row = PERK_BY_ID.get(chosen_perk_id)
        perk_name_ru = (perk_row.name if perk_row else chosen_perk_id).strip()
        moment_ru = await generate_hire_waifu_perk_moment_ru(
            perk_id=chosen_perk_id,
            perk_name_ru=perk_name_ru,
            name=(name or "Наёмница").strip(),
            race_ru=race_ru,
            class_ru=class_ru,
            bio=bio,
        )
        if moment_ru:
            pose_snippet = moment_ru
            logger.info(
                "[HIRE PORTRAIT MOMENT] perk_id=%s source=ai preview=%s",
                chosen_perk_id,
                moment_ru[:120].replace("\n", " "),
            )
        else:
            logger.warning(
                "[HIRE PORTRAIT MOMENT] perk_id=%s source=fallback_pool (AI empty or failed)",
                chosen_perk_id,
            )
    base_tail = (
        "absurd comedy anime, surreal gag energy, oddly specific funny detail, "
        "lighthearted chaos, clean soft lighting, upper body, detailed face, "
        "high quality illustration, 1girl, wholesome chaos not horror"
    )
    parts: list[str] = [
        "anime style portrait",
        race_visual,
        class_visual,
    ]
    if perk_snippet:
        parts.append(perk_snippet)
    parts.append(pose_snippet)
    parts.append(base_tail)
    prompt = ", ".join(parts)

    logger.info("[IMAGE GEN] Starting for %s (%s), model: %s provider=routerai", name or "waifu", race_ru, model)
    if chosen_perk_id:
        logger.info("[IMAGE GEN] Chosen perk for portrait: %s", chosen_perk_id)
    logger.info("[IMAGE GEN] Prompt: %s...", prompt[:100])

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            last_choice: dict = {}
            for modalities in IMAGE_MODALITY_ATTEMPTS:
                body = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "modalities": list(modalities),
                    "image_config": {
                        "aspect_ratio": "2:3",
                        "image_size": "1K",
                    },
                }
                r = await post_chat_completions(
                    client,
                    body,
                    caller="hire portrait image",
                    use_image_model=True,
                )
                logger.info("[IMAGE GEN] Status: %s modalities=%s", r.status_code, modalities)

                if r.status_code == 401:
                    logger.error("[IMAGE GEN] LLM: неверный API ключ (401)")
                    return None
                if not r.is_success:
                    logger.error("[IMAGE GEN] Error body: %s", r.text[:500])
                    return None

                data = r.json()
                choices = data.get("choices") or []
                if not isinstance(choices, list) or not choices:
                    logger.warning("[IMAGE GEN] No choices modalities=%s", modalities)
                    continue
                first = choices[0]
                if not isinstance(first, dict):
                    logger.warning("[IMAGE GEN] choices[0] is not dict: %s", type(first))
                    continue
                last_choice = first
                message = first.get("message") or {}
                message = message if isinstance(message, dict) else {}
                logger.info("[IMAGE GEN] Response keys: %s", list(message.keys()))
                b64_out = await _extract_openrouter_image_b64(message, client)
                if b64_out:
                    return b64_out
                _log_image_parse_miss(
                    "IMAGE GEN",
                    modalities=modalities,
                    choice=first,
                    usage=data.get("usage"),
                )

            logger.warning(
                "[IMAGE GEN] Image not found. last_choice=%s",
                _summarize_image_choice_for_log(last_choice),
            )
            return None
    except httpx.TimeoutException:
        logger.error("[IMAGE GEN] RouterAI image: timeout (120s)")
        return None
    except Exception as e:
        logger.exception("[IMAGE GEN] Exception: %s", e)
        return None
