"""On-demand tavern chat. Not used by GET /delve/sync."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db import models as m
from waifu_bot.services.delve import DelveError

CHAT_DAY_CAP = 12
HISTORY_CAP = 16


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def chat_left(card: m.CompanionCard, *, now: datetime | None = None) -> int:
    voice = card.voice or {}
    day = (now or datetime.now(timezone.utc)).date().isoformat()
    if str(voice.get("chat_day") or "") != day:
        return CHAT_DAY_CAP
    return max(0, CHAT_DAY_CAP - int(voice.get("chat_n") or 0))


def _bump_chat(card: m.CompanionCard) -> None:
    voice = dict(card.voice or {})
    day = _today()
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
            from waifu_bot.services.companion_living import patron_name

            patron = await patron_name(session, player_id)
            look = dict(card.look_card or {})
            if patron and look.get("hired_by") != patron:
                look["hired_by"] = patron
                card.look_card = look
            system = (
                f"Ты {card.name}, наёмница отряда {patron}. "
                f"{patron} — основная вайфу; она тебя наняла, вы ходите в колонну вместе. "
                f"Сейчас она говорит с тобой у очага в таверне. "
                f"Стойка: {stance}. Нрав: {temper}. Черты: {traits}. "
                f"Био: {(card.bio or '')[:400]}. Голос: {voice_line or 'сухо'}. "
                f"Больные места (не веди себя вежливо, если задели): {', '.join(sores) or 'нет'}. "
                f"Собеседник — {patron}, не случайный гость. "
                "Не называй её путницей, странницей, незнакомкой, госпожой с дороги. "
                "Обращайся на «ты», как к своей, можно по имени. "
                "Ответ 1–3 коротких предложения, по-русски. Не отрицай раны. Не JSON. "
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
                            reply = msg.strip()[:400]
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
