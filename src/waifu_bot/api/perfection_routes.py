"""API системы совершенствования (post-60)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from waifu_bot.api.deps import get_db, get_player_id
from waifu_bot.db import models as m
from waifu_bot.services import perfection as perfection_svc

logger = logging.getLogger(__name__)

router = APIRouter(tags=["perfection"])


class PerfectionChooseBody(BaseModel):
    pending_id: int
    option_index: int = Field(ge=0, le=2)


@router.get("/perfection")
async def get_perfection(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    res = await session.execute(
        select(m.Player)
        .options(selectinload(m.Player.main_waifu))
        .where(m.Player.id == int(player_id))
    )
    player = res.scalar_one_or_none()
    if not player:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="player_not_found")
    waifu = player.main_waifu
    if waifu is not None:
        await perfection_svc.unlock_perfection_if_needed(session, player, waifu)
        await session.commit()
    state = await perfection_svc.get_state(session, player)
    return state


@router.post("/perfection/choose")
async def choose_perfection(
    body: PerfectionChooseBody,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    res = await session.execute(
        select(m.Player)
        .options(selectinload(m.Player.main_waifu))
        .where(m.Player.id == int(player_id))
    )
    player = res.scalar_one_or_none()
    if not player:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="player_not_found")
    try:
        state = await perfection_svc.choose_pending(
            session,
            player,
            pending_id=int(body.pending_id),
            option_index=int(body.option_index),
        )
        await session.commit()
    except ValueError as e:
        code = str(e) or "choose_failed"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=code) from e
    except Exception:
        logger.exception("perfection choose failed player_id=%s", player_id)
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="choose_failed")
    return state
