"""Player profile API: avatar, showcase, campaign, public guild view."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.api.deps import get_db, get_player_id
from waifu_bot.services import player_profile_service as pps

logger = logging.getLogger(__name__)

router = APIRouter()


class PlayerProfilePatchBody(BaseModel):
    avatar_preset_id: int | None = None
    clear_custom_avatar: bool = False
    profile_showcase: Literal["portrait", "paperdoll"] | None = None


def _static_root() -> Path:
    return Path(__file__).resolve().parents[3] / "static"


def _profile_error(exc: ValueError) -> HTTPException:
    code = str(exc)
    status_code = status.HTTP_400_BAD_REQUEST
    if code in ("player_not_found",):
        status_code = status.HTTP_404_NOT_FOUND
    elif code in ("not_same_guild",):
        status_code = status.HTTP_403_FORBIDDEN
    return HTTPException(status_code=status_code, detail=code)


@router.get("/player/profile", tags=["player"])
async def get_player_profile_self(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    try:
        return await pps.get_self_profile(session, player_id)
    except ValueError as e:
        raise _profile_error(e) from e


@router.patch("/player/profile", tags=["player"])
async def patch_player_profile_self(
    body: PlayerProfilePatchBody,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    try:
        return await pps.patch_self_profile(
            session,
            player_id,
            avatar_preset_id=body.avatar_preset_id,
            clear_custom_avatar=body.clear_custom_avatar,
            profile_showcase=body.profile_showcase,
        )
    except ValueError as e:
        raise _profile_error(e) from e


@router.post("/player/avatar/upload", tags=["player"])
async def upload_player_avatar(
    file: UploadFile = File(...),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    raw = await file.read()
    try:
        return await pps.upload_player_avatar(
            session, player_id, raw, file.content_type, _static_root()
        )
    except ValueError as e:
        code = str(e)
        if code == "file_too_large":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": code, "max": pps.AVATAR_UPLOAD_MAX_BYTES},
            ) from e
        raise _profile_error(e) from e


@router.get("/player/campaign-progress", tags=["player"])
async def get_player_campaign_progress(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    return await pps.build_campaign_progress(session, player_id)


@router.get("/player/{target_player_id}/profile", tags=["player"])
async def get_player_profile_public(
    target_player_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    try:
        return await pps.get_public_profile(session, player_id, int(target_player_id))
    except ValueError as e:
        raise _profile_error(e) from e
