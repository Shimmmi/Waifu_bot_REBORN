"""Activity economy API (Steam clicks + Mobile steps)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.api.deps import get_db, get_player_id, get_redis
from waifu_bot.game.economy import SOURCE_MOBILE_STEPS, SOURCE_STEAM_CLICKS
from waifu_bot.services.activity_combat import claim_activity_input, get_activity_status
from waifu_bot.services.activity_starter import ensure_activity_starter_gear
from waifu_bot.services.combat import CombatService

router = APIRouter(prefix="/activity", tags=["activity"])

_combat = CombatService(redis_client=get_redis())


class ActivityClaimIn(BaseModel):
    source: str = Field(..., description=f"{SOURCE_MOBILE_STEPS} | {SOURCE_STEAM_CLICKS}")
    units: int = Field(0, ge=0, le=100_000)
    client_counter_total: int | None = Field(None, ge=0)
    client_window_ms: int | None = Field(None, ge=0)


class ActivityClaimOut(BaseModel):
    accepted_units: int
    buffer_left: int
    min_chars: int = 1
    hits_applied: int
    rejected_reason: str | None = None
    units_to_next_hit: int = 0
    results: list[dict] = Field(default_factory=list)
    source: str | None = None
    economy: str = "activity"


@router.get("/status")
async def activity_status(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
    ensure_starter: bool = Query(True),
):
    if ensure_starter:
        await ensure_activity_starter_gear(session, player_id)
        await session.commit()
    return await get_activity_status(session, player_id)


@router.post("/input/claim", response_model=ActivityClaimOut)
async def activity_input_claim(
    body: ActivityClaimIn,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    await ensure_activity_starter_gear(session, player_id)
    out = await claim_activity_input(
        session,
        player_id,
        source=body.source,
        units=body.units,
        client_counter_total=body.client_counter_total,
        client_window_ms=body.client_window_ms,
        combat_service=_combat,
    )
    return ActivityClaimOut(**{k: out[k] for k in ActivityClaimOut.model_fields if k in out})


@router.post("/starter/ensure")
async def activity_ensure_starter(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    inv = await ensure_activity_starter_gear(session, player_id)
    await session.commit()
    return {
        "ok": True,
        "granted": inv is not None,
        "inventory_item_id": inv.id if inv else None,
    }
