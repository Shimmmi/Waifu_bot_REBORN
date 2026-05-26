"""API routes for group chat activity rewards."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.api.deps import get_db, get_player_id, get_redis
from waifu_bot.services import chat_rewards as chat_rewards_svc

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/chat-rewards/status", tags=["chat-rewards"])
async def chat_rewards_status(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    return await chat_rewards_svc.get_status(session, redis, player_id)


@router.post("/chat-rewards/claim", tags=["chat-rewards"])
async def chat_rewards_claim(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    result = await chat_rewards_svc.claim_wallet(session, redis, player_id)
    if not result.ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error or "claim_failed",
        )
    await session.commit()
    return {
        "ok": True,
        "gold": result.gold,
        "exp": result.exp,
        "chests": result.chests,
        "level_before": result.level_before,
        "level_after": result.level_after,
        "level_up": result.level_after > result.level_before,
        "items": result.items,
    }
