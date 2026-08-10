"""Phantom day-text buffer for GD word stats (RouterAI).

Privacy:
- Not for admin reading; never mirror into PostgreSQL / battle_logs / app logs.
- Redis-only, TTL-bound; purged after end-of-day analysis (and on cycle finish).
- Stores truncated message bodies solely to compute top-5 words at 04:00 MSK.
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

REDIS_GD_PHANTOM_TXT = "gd_phantom_txt:"
REDIS_GD_PHANTOM_UCNT = "gd_phantom_ucnt:"

PHANTOM_TTL_SEC = 36 * 3600
MAX_CHARS_PER_MSG = 400
MAX_MSGS_PER_USER = 300
MAX_ENTRIES_PER_CYCLE = 8000


def phantom_list_key(cycle_id: int) -> str:
    return f"{REDIS_GD_PHANTOM_TXT}{int(cycle_id)}"


def phantom_ucnt_key(cycle_id: int) -> str:
    return f"{REDIS_GD_PHANTOM_UCNT}{int(cycle_id)}"


async def append_phantom_text(
    redis: Any,
    cycle_id: int,
    user_id: int,
    text: str | None,
) -> bool:
    """Append one truncated text for an enrolled participant. Returns True if stored."""
    if not redis:
        return False
    body = (text or "").strip()
    if not body:
        return False
    if len(body) > MAX_CHARS_PER_MSG:
        body = body[:MAX_CHARS_PER_MSG]
    cid = int(cycle_id)
    uid = int(user_id)
    list_key = phantom_list_key(cid)
    ucnt_key = phantom_ucnt_key(cid)
    try:
        total = await redis.llen(list_key)
        if int(total or 0) >= MAX_ENTRIES_PER_CYCLE:
            return False
        raw_ucnt = await redis.hget(ucnt_key, str(uid))
        ucnt = int(raw_ucnt or 0)
        if ucnt >= MAX_MSGS_PER_USER:
            return False
        payload = json.dumps({"u": uid, "t": body}, ensure_ascii=False, separators=(",", ":"))
        await redis.rpush(list_key, payload)
        await redis.hincrby(ucnt_key, str(uid), 1)
        await redis.expire(list_key, PHANTOM_TTL_SEC)
        await redis.expire(ucnt_key, PHANTOM_TTL_SEC)
        return True
    except Exception:
        logger.debug(
            "GD phantom append failed cycle=%s uid=%s",
            cid,
            uid,
            exc_info=True,
        )
        return False


async def load_phantom_log(redis: Any, cycle_id: int) -> dict[int, list[str]]:
    """Load phantom messages grouped by user_id. Never log message bodies."""
    out: dict[int, list[str]] = {}
    if not redis:
        return out
    try:
        raw_items = await redis.lrange(phantom_list_key(int(cycle_id)), 0, -1)
    except Exception:
        logger.debug("GD phantom load failed cycle=%s", cycle_id, exc_info=True)
        return out
    for raw in raw_items or []:
        try:
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8", errors="replace")
            obj = json.loads(raw)
            uid = int(obj.get("u") or 0)
            text = str(obj.get("t") or "").strip()
            if uid <= 0 or not text:
                continue
            out.setdefault(uid, []).append(text)
        except Exception:
            continue
    return out


async def purge_phantom_log(redis: Any, cycle_id: int) -> None:
    """Delete phantom keys for a cycle (best-effort)."""
    if not redis:
        return
    cid = int(cycle_id)
    try:
        await redis.delete(phantom_list_key(cid), phantom_ucnt_key(cid))
    except Exception:
        logger.debug("GD phantom purge failed cycle=%s", cid, exc_info=True)
