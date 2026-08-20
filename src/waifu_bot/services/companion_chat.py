"""On-demand tavern chat. Not used by GET /delve/sync."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db import models as m
from waifu_bot.game.delve_catalog import msk_today
from waifu_bot.services.delve import DelveError

CHAT_DAY_CAP = 12
HISTORY_CAP = 16
_STAGE_LINE = re.compile(r"^\*[^*\n]{2,40}\*\s*")
_STAGE_TAIL = re.compile(r"\s*\*[^*\n]{2,40}\*\s*$")

logger = logging.getLogger(__name__)


def _today(now: datetime | None = None) -> str:
    return msk_today(now or datetime.now(timezone.utc))


def chat_left(card: m.CompanionCard, *, now: datetime | None = None) -> int:
    voice = card.voice or {}
    day = _today(now)
    if str(voice.get("chat_day") or "") != day:
        return CHAT_DAY_CAP
    return max(0, CHAT_DAY_CAP - int(voice.get("chat_n") or 0))


def _bump_chat(card: m.CompanionCard, *, now: datetime | None = None) -> None:
    voice = dict(card.voice or {})
    day = _today(now)
    if str(voice.get("chat_day") or "") != day:
        voice["chat_day"] = day
        voice["chat_n"] = 0
    voice["chat_n"] = int(voice.get("chat_n") or 0) + 1
    card.voice = voice


def _history_messages(history: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for turn in (history or [])[-HISTORY_CAP:]:
        role = str((turn or {}).get("role") or "")
        text = str((turn or {}).get("text") or "").strip()[:400]
        if role not in ("user", "assistant") or not text:
            continue
        out.append({"role": role, "content": text})
    return out


def strip_stage_directions(text: str) -> str:
    """Drop *stage direction* only at line start/end. Keep mid-line *emphasis*."""
    raw = str(text or "")
    kept: list[str] = []
    for line in raw.splitlines() or [raw]:
        line = _STAGE_LINE.sub("", line)
        line = _STAGE_TAIL.sub("", line)
        if line.strip():
            kept.append(line.strip())
    cleaned = " ".join(kept).strip()
    return cleaned or raw.strip()


def _user_word_count(history: list[dict[str, Any]] | None) -> tuple[int, int]:
    turns = 0
    words = 0
    for turn in history or []:
        if str((turn or {}).get("role") or "") != "user":
            continue
        text = str((turn or {}).get("text") or "").strip()
        if not text:
            continue
        turns += 1
        words += len(text.split())
    return turns, words


async def reply_as_card(
    session: AsyncSession,
    player_id: int,
    card_id: int,
    text: str,
    history: list[dict[str, Any]] | None = None,
) -> str:
    card = await session.get(m.CompanionCard, int(card_id))
    if card is None or int(card.player_id) != int(player_id):
        raise DelveError("not_found", 404)
    if card.status not in ("living", "rain"):
        raise DelveError("cannot_chat", 400)
    if chat_left(card) <= 0:
        raise DelveError("chat_day_cap", 429)
    canned = _canned(card, text)
    reply = canned
    try:
        from waifu_bot.services.delve_line import _fast_model
        from waifu_bot.services.llm_client import has_text_llm_configured, post_chat_completions_routerai

        if has_text_llm_configured():
            sores = []
            for row in card.flesh or []:
                if isinstance(row, dict) and row.get("part"):
                    sores.append(str(row["part"]))
            traits = ", ".join(card.traits or [])
            voice_line = str((card.voice or {}).get("line") or "")
            stance = {"scout": "разведчица", "shield": "со щитом", "guide": "проводница"}.get(
                card.stance, card.stance
            )
            temper = {"curiosity": "любопытство", "temper": "вспыльчивость", "stay": "стойкость"}.get(
                card.temper, card.temper
            )
            from waifu_bot.services.companion_living import card_loyalty, patron_name

            patron = await patron_name(session, player_id)
            look = dict(card.look_card or {})
            if patron and look.get("hired_by") != patron:
                look["hired_by"] = patron
                card.look_card = look
            race_ru = str(look.get("race_ru") or "")
            class_ru = str(look.get("class_ru") or "")
            loyalty = card_loyalty(card)
            system = (
                f"Ты {card.name}, наёмница отряда {patron}. "
                f"{patron} — основная вайфу; она тебя наняла, вы ходите в колонну вместе. "
                f"Сейчас она говорит с тобой у очага в таверне. "
                f"Раса: {race_ru or '—'}. Класс: {class_ru or '—'}. "
                f"Стойка: {stance}. Нрав: {temper}. Черты: {traits}. "
                f"Лояльность к {patron}: {loyalty} из 100. "
                f"Био: {card.bio or ''}. Голос: {voice_line or 'сухо'}. "
                f"Больные места (не веди себя вежливо, если задели): {', '.join(sores) or 'нет'}. "
                f"Собеседник — {patron}, не случайный гость. "
                "Не называй её путницей, странницей, незнакомкой, госпожой с дороги. "
                "Обращайся на «ты», как к своей, можно по имени. "
                "Ответ 1–3 коротких предложения, по-русски. Только реплика. "
                "Без сценических ремарок, без *действий*, без (жестов), без описаний тела. "
                "Не отрицай раны. Не JSON. "
                "Держи нить разговора. Не ставь флаги, не открывай тайны журнала, которых не было."
            )
            messages = [{"role": "system", "content": system}, *_history_messages(history)]
            messages.append({"role": "user", "content": f"{patron} говорит: {text[:400]}"})
            async with httpx.AsyncClient(timeout=12.0) as client:
                r = await post_chat_completions_routerai(
                    client,
                    {
                        "messages": messages,
                        "max_tokens": 120,
                        "temperature": 0.85,
                        "reasoning": {"exclude": True},
                    },
                    model=_fast_model(),
                    caller="tavern living chat",
                )
                if r.status_code == 200:
                    data = r.json()
                    choices = data.get("choices") or []
                    if choices:
                        msg = (choices[0].get("message") or {}).get("content") or ""
                        if isinstance(msg, str) and msg.strip():
                            reply = strip_stage_directions(msg.strip())[:400]
    except Exception:
        reply = canned
    _bump_chat(card)
    await session.flush()
    return reply


def _canned(card: m.CompanionCard, text: str) -> str:
    low = text.lower()
    for row in card.flesh or []:
        part = str((row or {}).get("part") or "")
        if part and part in low:
            return "Не твоё дело. Сидит."
        if part == "рука" and ("рук" in low or "hand" in low):
            return "Спроси ещё раз — выйдешь без зуба."
    if card.temper == "temper":
        return "Ну. Говори."
    if card.temper == "curiosity":
        return "Ну. Слушаю."
    return "Сижу. Не скучаю."


async def _score_loyalty_delta(
    card: m.CompanionCard,
    history: list[dict[str, Any]],
    patron: str,
) -> int:
    from waifu_bot.services.delve_line import _fast_model
    from waifu_bot.services.llm_client import has_text_llm_configured, post_chat_completions_routerai

    if not has_text_llm_configured():
        return 0
    traits = ", ".join(card.traits or [])
    look = card.look_card or {}
    lines = []
    for turn in history[-HISTORY_CAP:]:
        role = str((turn or {}).get("role") or "")
        text = str((turn or {}).get("text") or "").strip()[:400]
        if role not in ("user", "assistant") or not text:
            continue
        who = patron if role == "user" else card.name
        lines.append(f"{who}: {text}")
    transcript = "\n".join(lines)[:1800]
    prompt = (
        'Ответь строго JSON: {"delta":1} или {"delta":-1} или {"delta":0}.\n'
        f"Ты оцениваешь, как диалог с {patron} сдвинул лояльность наёмницы {card.name}.\n"
        f"Раса: {look.get('race_ru')}. Класс: {look.get('class_ru')}. "
        f"Нрав: {card.temper}. Черты: {traits}. Био: {card.bio or ''}.\n"
        "delta=1 если разговор тёплый, уважительный, свой. "
        "delta=-1 если грубость, оскорбления, унижение, холодный расчёт. "
        "delta=0 если пусто, нейтрально или неясно. Только одно число.\n"
        f"Диалог:\n{transcript}"
    )
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await post_chat_completions_routerai(
                client,
                {
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 40,
                    "temperature": 0.2,
                    "reasoning": {"exclude": True},
                },
                model=_fast_model(),
                caller="tavern living loyalty",
            )
            if r.status_code != 200:
                return 0
            data = r.json()
            choices = data.get("choices") or []
            msg = ""
            if choices:
                msg = str((choices[0].get("message") or {}).get("content") or "")
            text = msg.strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)
            parsed = json.loads(text)
            delta = int(parsed.get("delta", 0))
            if delta > 0:
                return 1
            if delta < 0:
                return -1
            return 0
    except Exception:
        logger.warning("loyalty score failed card=%s", getattr(card, "id", None), exc_info=True)
        return 0


async def loyalty_tick(
    session: AsyncSession,
    player_id: int,
    card_id: int,
    history: list[dict[str, Any]] | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    card = await session.get(m.CompanionCard, int(card_id))
    if card is None or int(card.player_id) != int(player_id):
        raise DelveError("not_found", 404)
    from waifu_bot.services.companion_living import (
        card_loyalty,
        card_public,
        hall_dismiss_flags,
        leave_loyalty,
        patron_name,
    )

    dismiss_left, is_admin = await hall_dismiss_flags(session, player_id, now=now)
    party = (
        await session.execute(
            select(m.CompanionCard).where(
                m.CompanionCard.player_id == int(player_id),
                m.CompanionCard.slot.is_not(None),
            )
        )
    ).scalars().all()

    def payload(*, delta: int = 0, left: bool = False) -> dict[str, Any]:
        return {
            **card_public(
                card,
                now=now,
                party=list(party),
                dismiss_left=dismiss_left,
                is_admin=is_admin,
            ),
            "delta": delta,
            "left": left,
        }

    if card.status != "living":
        return payload()
    look = dict(card.look_card or {})
    day = _today(now)
    if str(look.get("loyalty_tick_msk") or "") == day:
        return payload()
    turns, words = _user_word_count(history)
    if turns < 1 or words < 2:
        return payload()
    patron = await patron_name(session, player_id)
    delta = await _score_loyalty_delta(card, history or [], patron)
    loyalty = max(0, min(100, card_loyalty(card) + int(delta)))
    look["loyalty"] = loyalty
    look["loyalty_tick_msk"] = day
    card.look_card = look
    left = False
    if loyalty <= 0:
        await leave_loyalty(session, player_id, int(card.id), now=now)
        left = True
    await session.flush()
    return payload(delta=delta, left=left)
