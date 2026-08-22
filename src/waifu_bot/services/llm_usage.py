"""Context + durable log for LLM HTTP roundtrips (no prompt bodies)."""

from __future__ import annotations

import logging
import re
from contextvars import ContextVar, Token
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Integer, func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_TZ_PLUS7 = timezone(timedelta(hours=7))
_ID_IN_PATH = re.compile(r"/\d+")

_player_id: ContextVar[int | None] = ContextVar("llm_player_id", default=None)
_source: ContextVar[str] = ContextVar("llm_source", default="background")
_trigger: ContextVar[str | None] = ContextVar("llm_trigger", default=None)

TokenList = list[Token]


def llm_player_id() -> int | None:
    return _player_id.get()


def llm_source() -> str:
    return _source.get() or "background"


def llm_trigger() -> str | None:
    return _trigger.get()


def set_llm_player_id(player_id: int | None) -> None:
    if player_id and int(player_id) > 0:
        _player_id.set(int(player_id))


def reset_llm_context(tokens: TokenList) -> None:
    for tok in reversed(tokens):
        tok.var.reset(tok)


def http_trigger(method: str, path: str) -> str:
    raw = (path or "").split("?", 1)[0]
    if raw.startswith("/api/"):
        raw = raw[4:]
    raw = _ID_IN_PATH.sub("/{id}", raw)
    return f"{method} {raw}"[:160]


def bind_llm_http(method: str, path: str) -> TokenList:
    return [
        _source.set("webapp"),
        _trigger.set(http_trigger(method, path)),
        _player_id.set(None),
    ]


def bind_llm_telegram(*, player_id: int | None, trigger: str | None) -> TokenList:
    return [
        _source.set("telegram"),
        _player_id.set(int(player_id) if player_id else None),
        _trigger.set((trigger or "")[:160] or None),
    ]


def telegram_trigger_from_text(text: str | None) -> str | None:
    raw = (text or "").strip()
    if not raw.startswith("/"):
        return None
    cmd = raw.split()[0].split("@", 1)[0]
    return cmd[:80] if cmd else None


def default_window_utc(
    since: datetime | None = None,
    until: datetime | None = None,
) -> tuple[datetime, datetime]:
    now_local = datetime.now(_TZ_PLUS7)
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    start = since or start_local.astimezone(timezone.utc)
    end = until or now_local.astimezone(timezone.utc)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return start, end


def usage_tokens_from_response(resp: Any) -> tuple[int | None, int | None]:
    try:
        data = resp.json()
        usage = data.get("usage") or {}
        pt = usage.get("prompt_tokens")
        ct = usage.get("completion_tokens")
        return (
            int(pt) if pt is not None else None,
            int(ct) if ct is not None else None,
        )
    except Exception:
        return None, None


async def record_llm_http(
    *,
    caller: str,
    modality: str,
    provider: str,
    model: str | None,
    http_status: int | None,
    ok: bool,
    latency_ms: int,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> None:
    """Insert one roundtrip. No-op if the API engine is not up. Never raises."""
    from waifu_bot.db.session import SessionLocal

    if SessionLocal is None:
        return
    try:
        from waifu_bot.db.models.llm_usage import LlmUsageLog

        row = LlmUsageLog(
            created_at=datetime.now(timezone.utc),
            caller=(caller or "unknown")[:80],
            modality="image" if modality == "image" else "text",
            player_id=llm_player_id(),
            source=(llm_source() or "background")[:16],
            trigger=((llm_trigger() or "")[:160] or None),
            provider=(provider or "unknown")[:32],
            model=(str(model)[:120] if model else None),
            http_status=http_status,
            ok=bool(ok),
            latency_ms=max(0, int(latency_ms)),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        async with SessionLocal() as session:
            session.add(row)
            await session.commit()
    except Exception:
        logger.warning("llm_usage_log insert failed caller=%s", caller, exc_info=True)


async def record_llm_response(
    *,
    caller: str,
    use_image_model: bool,
    provider: str,
    model: str | None,
    resp: Any | None,
    latency_ms: int,
) -> None:
    pt = ct = None
    status = None
    ok = False
    if resp is not None:
        status = getattr(resp, "status_code", None)
        ok = bool(getattr(resp, "is_success", False))
        pt, ct = usage_tokens_from_response(resp)
    await record_llm_http(
        caller=caller,
        modality="image" if use_image_model else "text",
        provider=provider,
        model=model,
        http_status=status,
        ok=ok,
        latency_ms=latency_ms,
        prompt_tokens=pt,
        completion_tokens=ct,
    )


async def usage_report(
    session: AsyncSession,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    modality: str | None = None,
    caller: str | None = None,
    player_id: int | None = None,
    recent_limit: int = 80,
) -> dict[str, Any]:
    from waifu_bot.db.models import Player
    from waifu_bot.db.models.llm_usage import LlmUsageLog

    start, end = default_window_utc(since, until)
    filters = [
        LlmUsageLog.created_at >= start,
        LlmUsageLog.created_at <= end,
    ]
    if modality in ("text", "image"):
        filters.append(LlmUsageLog.modality == modality)
    if caller:
        filters.append(LlmUsageLog.caller == caller.strip()[:80])
    if player_id:
        filters.append(LlmUsageLog.player_id == int(player_id))

    totals_row = (
        await session.execute(
            select(
                func.count().label("sent"),
                func.coalesce(func.sum(func.cast(LlmUsageLog.ok, Integer)), 0).label("ok"),
                func.coalesce(func.sum(LlmUsageLog.prompt_tokens), 0).label("prompt_tokens"),
                func.coalesce(func.sum(LlmUsageLog.completion_tokens), 0).label("completion_tokens"),
                func.count(func.distinct(LlmUsageLog.player_id)).label("players"),
            ).where(*filters)
        )
    ).one()
    sent = int(totals_row.sent or 0)
    ok_n = int(totals_row.ok or 0)

    by_caller_rows = (
        await session.execute(
            select(
                LlmUsageLog.caller,
                LlmUsageLog.modality,
                func.count().label("n"),
                func.coalesce(func.sum(func.cast(LlmUsageLog.ok, Integer)), 0).label("ok"),
                func.coalesce(func.avg(LlmUsageLog.latency_ms), 0).label("avg_ms"),
                func.coalesce(func.sum(LlmUsageLog.prompt_tokens), 0).label("prompt_tokens"),
                func.coalesce(func.sum(LlmUsageLog.completion_tokens), 0).label("completion_tokens"),
            )
            .where(*filters)
            .group_by(LlmUsageLog.caller, LlmUsageLog.modality)
            .order_by(func.count().desc())
            .limit(80)
        )
    ).all()

    by_player_rows = (
        await session.execute(
            select(
                LlmUsageLog.player_id,
                Player.username,
                Player.first_name,
                func.count().label("n"),
                func.coalesce(func.sum(func.cast(LlmUsageLog.ok, Integer)), 0).label("ok"),
                func.coalesce(func.sum(LlmUsageLog.prompt_tokens), 0).label("prompt_tokens"),
                func.coalesce(func.sum(LlmUsageLog.completion_tokens), 0).label("completion_tokens"),
            )
            .outerjoin(Player, Player.id == LlmUsageLog.player_id)
            .where(*filters)
            .group_by(LlmUsageLog.player_id, Player.username, Player.first_name)
            .order_by(func.count().desc())
            .limit(50)
        )
    ).all()

    recent_rows = (
        await session.execute(
            select(LlmUsageLog)
            .where(*filters)
            .order_by(LlmUsageLog.id.desc())
            .limit(max(1, min(200, recent_limit)))
        )
    ).scalars().all()

    return {
        "since": start.isoformat(),
        "until": end.isoformat(),
        "totals": {
            "sent": sent,
            "ok": ok_n,
            "error": max(0, sent - ok_n),
            "prompt_tokens": int(totals_row.prompt_tokens or 0),
            "completion_tokens": int(totals_row.completion_tokens or 0),
            "players": int(totals_row.players or 0),
        },
        "by_caller": [
            {
                "caller": r.caller,
                "modality": r.modality,
                "count": int(r.n),
                "ok": int(r.ok),
                "error": int(r.n) - int(r.ok),
                "avg_ms": int(r.avg_ms or 0),
                "prompt_tokens": int(r.prompt_tokens or 0),
                "completion_tokens": int(r.completion_tokens or 0),
            }
            for r in by_caller_rows
        ],
        "by_player": [
            {
                "player_id": r.player_id,
                "username": r.username,
                "first_name": r.first_name,
                "count": int(r.n),
                "ok": int(r.ok),
                "error": int(r.n) - int(r.ok),
                "prompt_tokens": int(r.prompt_tokens or 0),
                "completion_tokens": int(r.completion_tokens or 0),
            }
            for r in by_player_rows
        ],
        "recent": [
            {
                "id": row.id,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "player_id": row.player_id,
                "caller": row.caller,
                "source": row.source,
                "trigger": row.trigger,
                "modality": row.modality,
                "provider": row.provider,
                "model": row.model,
                "http_status": row.http_status,
                "ok": row.ok,
                "latency_ms": row.latency_ms,
                "prompt_tokens": row.prompt_tokens,
                "completion_tokens": row.completion_tokens,
            }
            for row in recent_rows
        ],
    }
