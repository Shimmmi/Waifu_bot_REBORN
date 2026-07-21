"""Merc overhaul API: debut, lineup, arena, exchange, ops board, perks."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.api.deps import get_db, get_player_id
from waifu_bot.services import merc_systems as merc_sys

logger = logging.getLogger(__name__)
router = APIRouter(tags=["merc"])


class DebutBody(BaseModel):
    template_id: str


class LineupBody(BaseModel):
    side: str = Field(..., pattern="^(atk|def)$")
    slot: int = Field(..., ge=1, le=3)
    waifu_id: Optional[int] = None


class FodderBody(BaseModel):
    target_id: int
    fodder_ids: list[int]


class ManualBody(BaseModel):
    waifu_id: int
    perk_id: str


class ConvertManualBody(BaseModel):
    waifu_id: int


class ArenaAttackBody(BaseModel):
    defender_id: Optional[int] = None
    bot: bool = False


class ExchangeBuyBody(BaseModel):
    item_id: str


@router.get("/tavern/merc-status")
async def merc_status(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    state = await merc_sys.get_or_create_tavern_state(session, player_id)
    cap = await merc_sys.bench_cap(session, player_id)
    count = await merc_sys.pool_count(session, player_id)
    return {
        **merc_sys.pity_status(state),
        "bench_cap": cap,
        "bench_count": count,
        "debut_options": merc_sys.debut_options() if not state.debut_legendary_done else [],
    }


@router.post("/tavern/debut-legendary")
async def debut_legendary(
    body: DebutBody,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await merc_sys.debut_legendary(session, player_id, body.template_id)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result)
    await session.commit()
    return result


@router.post("/tavern/lineup")
async def set_lineup(
    body: LineupBody,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await merc_sys.set_lineup_slot(
        session, player_id, side=body.side, slot=body.slot, waifu_id=body.waifu_id
    )
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result)
    await session.commit()
    return result


@router.get("/tavern/lineup")
async def get_lineup(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    return await merc_sys.get_lineup(session, player_id)


@router.post("/tavern/fodder-stars")
async def fodder_stars(
    body: FodderBody,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await merc_sys.fodder_for_stars(
        session, player_id, target_id=body.target_id, fodder_ids=body.fodder_ids
    )
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result)
    await session.commit()
    return result


@router.post("/tavern/convert-manual")
async def convert_manual(
    body: ConvertManualBody,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await merc_sys.convert_to_manual(session, player_id, body.waifu_id)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result)
    await session.commit()
    return result


@router.post("/tavern/apply-manual")
async def apply_manual(
    body: ManualBody,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await merc_sys.apply_manual_to_perk(
        session, player_id, waifu_id=body.waifu_id, perk_id=body.perk_id
    )
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result)
    await session.commit()
    return result


@router.get("/tavern/perks")
@router.get("/operations/perks")
@router.get("/expeditions/perks-v2")
async def merc_perks_catalog():
    return {"perks": merc_sys.perks_catalog()}


@router.get("/operations/board")
async def ops_board(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    board = await merc_sys.get_or_create_ops_board(session, player_id)
    await session.commit()
    return {"week_key": board.week_key, "contracts": board.contracts_json}


@router.get("/arena/status")
async def arena_status(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    st = await merc_sys.arena_status(session, player_id)
    await session.commit()
    return st


@router.get("/arena/opponents")
async def arena_opponents(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    return {"opponents": await merc_sys.arena_opponents(session, player_id)}


@router.post("/arena/attack")
async def arena_attack(
    body: ArenaAttackBody,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await merc_sys.arena_attack(
        session, player_id, defender_id=body.defender_id, bot=body.bot
    )
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result)
    await session.commit()
    return result


@router.get("/arena/history")
async def arena_history(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
    limit: int = Query(10, ge=1, le=50),
):
    from sqlalchemy import select

    from waifu_bot.db.models.merc_meta import MercArenaMatch

    rows = (
        await session.execute(
            select(MercArenaMatch)
            .where(MercArenaMatch.attacker_id == player_id)
            .order_by(MercArenaMatch.id.desc())
            .limit(limit)
        )
    ).scalars().all()
    return {
        "matches": [
            {
                "id": m.id,
                "winner": m.winner,
                "rating_delta": m.rating_delta,
                "rating_after": m.attacker_rating_after,
                "log": m.log_json,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in rows
        ]
    }


@router.get("/tavern/exchange")
async def exchange_catalog(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    state = await merc_sys.get_or_create_tavern_state(session, player_id)
    return {"items": merc_sys.EXCHANGE_CATALOG, "wallet": merc_sys.pity_status(state)}


@router.post("/tavern/exchange/buy")
async def exchange_buy(
    body: ExchangeBuyBody,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await merc_sys.exchange_buy(session, player_id, body.item_id)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result)
    await session.commit()
    return result


class GearEquipBody(BaseModel):
    waifu_id: int
    slot: str  # weapon|charm|relic
    item: Optional[dict] = None  # None = unequip; else {name, rarity, score}


@router.post("/tavern/gear/equip")
async def gear_equip(
    body: GearEquipBody,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.db.models import HiredWaifu
    from waifu_bot.game.merc_combat_rating import refresh_unit_power

    w = await session.get(HiredWaifu, int(body.waifu_id))
    if not w or int(w.player_id) != int(player_id):
        raise HTTPException(status_code=404, detail={"error": "waifu_not_found"})
    slot = body.slot.lower().strip()
    if slot not in ("weapon", "charm", "relic"):
        raise HTTPException(status_code=400, detail={"error": "invalid_slot"})
    attr = f"gear_{slot}"
    setattr(w, attr, body.item)
    score = 0
    for s in ("weapon", "charm", "relic"):
        g = getattr(w, f"gear_{s}", None) or {}
        if isinstance(g, dict):
            score += int(g.get("score") or g.get("rarity") or 0)
    w.gear_score_cache = score
    refresh_unit_power(w)
    await session.commit()
    return {"ok": True, "gear_score": score, "power": w.power}


@router.get("/tavern/codex")
async def tavern_codex(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    return {"legendaries": await merc_sys.codex_list(session, player_id)}
