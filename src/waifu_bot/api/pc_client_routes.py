"""Batched mouse/keyboard hits from the Steam desktop client.

Aligned with the activity economy: each click is one TEXT character unit.
Delegates to ``/api/activity/input/claim`` logic (source=steam_clicks).
The legacy STICKER + skip_spam_check path is removed.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.api.deps import get_db, get_player_id, get_redis
from waifu_bot.game.economy import SOURCE_STEAM_CLICKS
from waifu_bot.services.activity_combat import claim_activity_input
from waifu_bot.services.activity_starter import ensure_activity_starter_gear
from waifu_bot.services.combat import CombatService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pc", tags=["pc_client"])

combat_service = CombatService(redis_client=get_redis())

# Soft per-request hint (activity claim still applies its own max_hits_per_claim).
MAX_HITS_PER_REQUEST = 10


class PcHitBatchIn(BaseModel):
    hit_count: int = Field(..., ge=0, le=1000)
    client_window_ms: int | None = Field(None, ge=0)


class PcHitBatchOut(BaseModel):
    requested: int
    applied: int
    rejected_reason: str | None = None
    result: dict
    buffer_left: int = 0
    accepted_units: int = 0


@router.post("/hits/batch", response_model=PcHitBatchOut)
async def submit_pc_hit_batch(
    body: PcHitBatchIn,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Steam clicks → activity TEXT units (1 click = 1 char)."""
    await ensure_activity_starter_gear(session, player_id)
    units = min(int(body.hit_count), MAX_HITS_PER_REQUEST * 20)  # allow buffer fill
    out = await claim_activity_input(
        session,
        player_id,
        source=SOURCE_STEAM_CLICKS,
        units=units,
        client_window_ms=body.client_window_ms,
        combat_service=combat_service,
    )
    last = (out.get("results") or [{}])[-1] if out.get("results") else {}
    rejected = out.get("rejected_reason")
    if body.hit_count > units and rejected is None:
        rejected = "batch_capped"
    return PcHitBatchOut(
        requested=body.hit_count,
        applied=int(out.get("hits_applied") or 0),
        rejected_reason=rejected,
        result=last or {"buffer_left": out.get("buffer_left")},
        buffer_left=int(out.get("buffer_left") or 0),
        accepted_units=int(out.get("accepted_units") or 0),
    )
