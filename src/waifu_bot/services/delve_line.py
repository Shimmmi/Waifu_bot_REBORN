"""Cheap one-line flavor for an open Expeditions tab. GET /delve/sync never imports this."""

from __future__ import annotations

import logging
import re

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.game.delve_catalog import NODE_LABEL_RU, PALETTE_BY_ID, STANCES, TEMPERS, phrase_for
from waifu_bot.services.delve import DelveError, build_frame, get_state_for_update, list_companions
from waifu_bot.services.llm_client import has_text_llm_configured, post_chat_completions_routerai

logger = logging.getLogger(__name__)

_MAX_CHARS = 180
_MAX_WORDS = 24


def flavor_cache_key(*, d: int, node: str, palette_id: str) -> str:
    return f"{int(d)}:{node}:{palette_id}"


def _sanitize_line(text: str, *, name: str) -> str | None:
    raw = (text or "").strip().strip('"“”«»')
    raw = re.sub(r"\s+", " ", raw)
    if not raw:
        return None
    first = raw.split(". ")[0].strip()
    if first and not first.endswith((".", "!", "…")):
        first = first + "."
    words = first.split()
    if len(words) > _MAX_WORDS:
        first = " ".join(words[:_MAX_WORDS]).rstrip(".,;:") + "."
    if len(first) > _MAX_CHARS:
        first = first[: _MAX_CHARS - 1].rstrip() + "…"
    lower = first.lower()
    if any(tok in lower for tok in ("http", "```", "lorem", "as an ai")):
        return None
    return first


def _fast_model() -> str:
    try:
        from waifu_bot.services.ai_presets import SinglePreset, resolve_preset

        cfg, _ = resolve_preset("fast")
        if isinstance(cfg, SinglePreset) and cfg.model:
            return str(cfg.model)
    except Exception:
        pass
    return "google/gemini-3.5-flash-lite"


async def _llm_line(
    *,
    name: str,
    stance: str,
    temper: str,
    node: str,
    palette_id: str,
    d: int,
) -> str | None:
    if not has_text_llm_configured():
        return None
    pal = PALETTE_BY_ID.get(palette_id, {}).get("label", palette_id)
    node_ru = NODE_LABEL_RU.get(node, node)
    stance_ru = STANCES.get(stance, {}).get("label", stance)
    temper_ru = TEMPERS.get(temper, {}).get("label", temper)
    prompt = (
        "Напиши ОДНО короткое предложение на русском (8–20 слов).\n"
        f"Героиня: {name}. Стойка: {stance_ru}. Нрав: {temper_ru}.\n"
        f"Место: {pal}. Узел: {node_ru}. Глубина: {d}.\n"
        "Они спускаются в шахту. Тон — тихий JRPG, без пафоса.\n"
        "Третье лицо, субъект — имя героини. Без кавычек, списков, английского, "
        "обращения к игроку и описания интерфейса."
    )
    model = _fast_model()
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await post_chat_completions_routerai(
                client,
                {
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 80,
                    "temperature": 0.85,
                    "reasoning": {"exclude": True},
                },
                model=model,
                caller="delve line",
            )
            if r.status_code != 200:
                logger.warning("delve line HTTP %s", r.status_code)
                return None
            data = r.json()
            choices = data.get("choices") or []
            if not choices or not isinstance(choices[0], dict):
                return None
            from waifu_bot.services.ai_narrative_rewrite import _extract_openrouter_assistant_text

            text = _extract_openrouter_assistant_text(choices[0])
            return _sanitize_line(text, name=name)
    except Exception:
        logger.warning("delve line failed", exc_info=True)
        return None


async def request_delve_line(session: AsyncSession, player_id: int) -> dict:
    from datetime import datetime, timezone

    from sqlalchemy import select

    from waifu_bot.db import models as m

    now = datetime.now(timezone.utc)
    state = await get_state_for_update(session, player_id)
    if state is None or state.t_origin is None:
        raise DelveError("not_started", 400)
    companions = await list_companions(session, player_id)
    mw = (
        await session.execute(select(m.MainWaifu).where(m.MainWaifu.player_id == int(player_id)))
    ).scalar_one_or_none()
    ov = int(mw.level or 1) if mw is not None else 1
    frame = build_frame(state, companions, now=now, ov_level=ov)
    key = flavor_cache_key(d=int(frame["d"]), node=str(frame["node"]), palette_id=str(frame["palette_id"]))
    cached = (state.flavor_text or "").strip()
    if state.flavor_key == key and cached:
        return {"phrase": cached, "from_llm": True, "cached": True}
    face = companions[0] if companions else None
    name = (face.name if face is not None else None) or "Она"
    template = phrase_for(
        node=str(frame["node"]),
        palette_id=str(frame["palette_id"]),
        name=name,
        spine_seed=int(state.spine_seed or 0),
        d=int(frame["d"]),
    )
    generated = None
    if face is not None:
        generated = await _llm_line(
            name=name,
            stance=str(face.stance or "guide"),
            temper=str(face.temper or "stay"),
            node=str(frame["node"]),
            palette_id=str(frame["palette_id"]),
            d=int(frame["d"]),
        )
    text = generated or template
    state.flavor_key = key
    state.flavor_text = text[:280]
    return {"phrase": text, "from_llm": bool(generated), "cached": False}
