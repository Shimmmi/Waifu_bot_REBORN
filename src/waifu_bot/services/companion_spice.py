"""LLM spice for already-resolved special beats. Not imported by GET /delve/sync."""

from __future__ import annotations

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db import models as m


async def spice_one(session: AsyncSession, player_id: int) -> dict | None:
    row = (
        await session.execute(
            select(m.CompanionEvent)
            .where(
                m.CompanionEvent.player_id == int(player_id),
                m.CompanionEvent.needs_prose.is_(True),
            )
            .order_by(m.CompanionEvent.id.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    card = await session.get(m.CompanionCard, int(row.card_id)) if row.card_id else None
    name = card.name if card else "Она"
    original = row.line_ru
    try:
        from waifu_bot.services.delve_line import _fast_model
        from waifu_bot.services.llm_client import has_text_llm_configured, post_chat_completions_routerai

        if has_text_llm_configured():
            async with httpx.AsyncClient(timeout=12.0) as client:
                r = await post_chat_completions_routerai(
                    client,
                    {
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "Перепиши одной-двумя фразами по-русски уже случившееся. "
                                    "Не меняй исход. Не добавляй золото, смерть или исцеление, если их нет в тексте."
                                ),
                            },
                            {"role": "user", "content": f"{name}. {original}"},
                        ],
                        "max_tokens": 80,
                        "temperature": 0.85,
                        "reasoning": {"exclude": True},
                    },
                    model=_fast_model(),
                    caller="tavern living spice",
                )
                if r.status_code == 200:
                    data = r.json()
                    choices = data.get("choices") or []
                    msg = ""
                    if choices:
                        msg = str((choices[0].get("message") or {}).get("content") or "").strip()
                    if msg:
                        row.line_ru = msg[:280]
                        payload = dict(row.payload or {})
                        payload["spiced"] = True
                        row.payload = payload
    except Exception:
        pass
    row.needs_prose = False
    return {"ok": True, "id": row.id, "phrase": row.line_ru, "original": original}
