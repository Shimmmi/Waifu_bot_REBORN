from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.api.deps import get_db, get_player_id
from waifu_bot.db import models as m
from waifu_bot.services.expedition import ExpeditionService

router = APIRouter()
service = ExpeditionService()


@router.get("/expeditions/slots", tags=["expedition"])
async def expedition_slots(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    day_key = datetime.utcnow().date()
    try:
        slots = await service.ensure_daily_slots(session, day_key)
    except SQLAlchemyError:
        return {"slots": []}
    except Exception:
        return {"slots": []}
    return {
        "slots": [
            {
                "id": s.id,
                "slot": s.slot,
                "name": s.name,
                "base_level": s.base_level,
                "base_difficulty": s.base_difficulty,
                "affixes": s.affixes,
                "base_gold": s.base_gold,
                "base_experience": s.base_experience,
            }
            for s in slots
        ]
    }


@router.get("/expeditions/active", tags=["expedition"])
async def expedition_active(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    try:
        active = await service.list_active(session, player_id)
    except SQLAlchemyError:
        return {"active": []}
    except Exception:
        return {"active": []}
    now = datetime.utcnow()
    return {
        "active": [
            {
                "id": e.id,
                "slot_id": e.expedition_slot_id,
                "duration_minutes": e.duration_minutes,
                "started_at": e.started_at,
                "ends_at": e.ends_at,
                "remaining_seconds": max(0, int((e.ends_at - now).total_seconds())),
                "chance": e.chance,
                "success": e.success,
                "reward_gold": e.reward_gold,
                "reward_experience": e.reward_experience,
                "squad_waifu_ids": e.squad_waifu_ids,
                "cancelled": e.cancelled,
                "claimed": e.claimed,
            }
            for e in active
        ]
    }


@router.post("/expeditions/start", tags=["expedition"])
async def expedition_start(
    slot_id: int = Query(..., ge=1),
    duration_minutes: int = Query(..., ge=15),
    squad_ids: list[int] = Query(...),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    try:
        expedition = await service.start_expedition(session, player_id, slot_id, duration_minutes, squad_ids)
    except SQLAlchemyError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="expedition_storage_unavailable")
    except Exception:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="expedition_unavailable")
    except ValueError as exc:
        detail = str(exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    return {
        "id": expedition.id,
        "chance": expedition.chance,
        "success": expedition.success,
        "reward_gold": expedition.reward_gold,
        "reward_experience": expedition.reward_experience,
        "ends_at": expedition.ends_at,
    }


@router.post("/expeditions/cancel", tags=["expedition"])
async def expedition_cancel(
    expedition_id: int = Query(..., ge=1),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    try:
        expedition = await service.cancel_expedition(session, expedition_id, player_id)
    except SQLAlchemyError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="expedition_storage_unavailable")
    except Exception:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="expedition_unavailable")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return {
        "id": expedition.id,
        "cancelled": expedition.cancelled,
        "reward_gold": expedition.reward_gold,
        "reward_experience": expedition.reward_experience,
    }


@router.post("/expeditions/claim", tags=["expedition"])
async def expedition_claim(
    expedition_id: int = Query(..., ge=1),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    try:
        expedition = await service.claim_rewards(session, expedition_id, player_id)
    except SQLAlchemyError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="expedition_storage_unavailable")
    except Exception:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="expedition_unavailable")
    except ValueError as exc:
        detail = str(exc)
        code = status.HTTP_400_BAD_REQUEST if detail == "not_ready" else status.HTTP_404_NOT_FOUND
        raise HTTPException(status_code=code, detail=detail)
    return {
        "id": expedition.id,
        "claimed": expedition.claimed,
        "reward_gold": expedition.reward_gold,
        "reward_experience": expedition.reward_experience,
        "finished_at": expedition.finished_at,
    }


@router.get("/expeditions/waifus", tags=["expedition"])
async def expedition_waifus(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
    limit: Optional[int] = Query(30, ge=1, le=100),
):
    try:
        result = await session.execute(
            select(m.HiredWaifu).where(m.HiredWaifu.player_id == player_id).limit(limit)
        )
        waifus = result.scalars().all()
    except SQLAlchemyError:
        return {"waifus": []}
    except Exception:
        return {"waifus": []}
    return {
        "waifus": [
            {
                "id": w.id,
                "name": w.name,
                "race": w.race,
                "class": w.class_,
                "rarity": w.rarity,
                "level": w.level,
                "power": w.power,
                "perks": w.perks,
            }
            for w in waifus
        ]
    }
