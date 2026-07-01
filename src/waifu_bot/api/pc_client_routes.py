"""Batched mouse/keyboard "hits" from the Steam desktop client.

The Electron client (desktop_client/) counts raw mouse clicks and key presses
locally and periodically flushes a small batch to this endpoint instead of
making one HTTP request per click (see input_tracker.js). This route does
NOT introduce a new damage/balance path: each unit of the batch is applied
by calling the *existing* CombatService.process_message_damage() exactly the
way the WebApp "continue" button already does (see /dungeons/continue in
dungeon_routes.py), and is subject to the *same* Redis-backed per-player
spam gate (MAX_MESSAGES_PER_WINDOW / SPAM_WINDOW_SECONDS) as Telegram
messages and WebApp clicks — a player linked to the same player_id via
Steam cannot out-pace the existing rate limit by batching more clicks.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.api.deps import get_db, get_player_id, get_redis
from waifu_bot.game.constants import MediaType
from waifu_bot.services.combat import CombatService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pc", tags=["pc_client"])

combat_service = CombatService(redis_client=get_redis())

# Upper bound on how many hits a single HTTP request will ever try to apply,
# regardless of what the client reports. The real pacing is enforced by
# CombatService's existing spam gate (shared with Telegram/WebApp); this is
# just a sane ceiling on per-request DB work. Calibrate on staging (Этап 2
# follow-up) once real click cadence from the Electron tracker is measured.
MAX_HITS_PER_REQUEST = 10


class PcHitBatchIn(BaseModel):
    # How many raw clicks/keypresses the client observed since the last flush.
    hit_count: int = Field(..., ge=0, le=1000)
    # Client-side batching window, informational only (not trusted for pacing).
    client_window_ms: int | None = Field(None, ge=0)


class PcHitBatchOut(BaseModel):
    requested: int
    applied: int
    rejected_reason: str | None = None
    result: dict


@router.post("/hits/batch", response_model=PcHitBatchOut)
async def submit_pc_hit_batch(
    body: PcHitBatchIn,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    applied = 0
    rejected_reason: str | None = None
    last_result: dict = {}

    to_apply = min(body.hit_count, MAX_HITS_PER_REQUEST)
    for _ in range(to_apply):
        last_result = await combat_service.process_message_damage(
            session,
            player_id,
            MediaType.STICKER,
            message_text=None,
            message_length=0,
        )
        if last_result.get("error"):
            # spam_detected / no_active_battle / no_waifu / no_monster / abyss_session_active etc. —
            # nothing more to do this batch, stop early instead of repeating the same error.
            rejected_reason = last_result["error"]
            break
        applied += 1

    if body.hit_count > MAX_HITS_PER_REQUEST and rejected_reason is None:
        rejected_reason = "batch_capped"

    return PcHitBatchOut(
        requested=body.hit_count,
        applied=applied,
        rejected_reason=rejected_reason,
        result=last_result,
    )
