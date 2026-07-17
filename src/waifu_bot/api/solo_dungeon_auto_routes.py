"""API routes for solo dungeon auto-restart preferences."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.api import schemas
from waifu_bot.api.deps import get_db, get_player_id
from waifu_bot.db.models.player import Player
from waifu_bot.services import solo_dungeon_auto_prefs as prefs_svc

router = APIRouter()


def _prefs_response(player: Player) -> schemas.SoloDungeonAutoPrefsOut:
    p = prefs_svc.get_prefs(player)
    return schemas.SoloDungeonAutoPrefsOut(**p)


@router.get(
    "/player/solo-dungeon-auto-prefs",
    response_model=schemas.SoloDungeonAutoPrefsOut,
    tags=["player"],
)
async def get_solo_dungeon_auto_prefs(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    player = await session.get(Player, player_id)
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="player_not_found")
    return _prefs_response(player)


@router.patch(
    "/player/solo-dungeon-auto-prefs",
    response_model=schemas.SoloDungeonAutoPrefsOut,
    tags=["player"],
)
async def patch_solo_dungeon_auto_prefs(
    body: schemas.SoloDungeonAutoPrefsPatch,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    player = await session.get(Player, player_id)
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="player_not_found")
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="empty_patch")
    prefs_svc.merge_patch(player, patch)
    await session.commit()
    return _prefs_response(player)
