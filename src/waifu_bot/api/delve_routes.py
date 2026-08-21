"""Delve column API. GET /delve/sync never calls a language model."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.api.deps import get_db, get_player_id
from waifu_bot.services.delve import (
    DelveError,
    grant_and_sync,
    reform_delve,
    start_delve,
    tint_sleeve,
)
from waifu_bot.services.delve_flag import is_delve_enabled
from waifu_bot.services.delve_portraits import generate_companion_portrait, portrait_file
from waifu_bot.services.game_config_service import get_game_config_map

logger = logging.getLogger(__name__)
router = APIRouter(tags=["delve"])


def _raise(err: DelveError) -> None:
    raise HTTPException(status_code=err.http_status, detail=err.code) from err


async def _require_delve(session: AsyncSession) -> None:
    cfg = await get_game_config_map(session)
    if not is_delve_enabled(cfg):
        raise HTTPException(status_code=404, detail="delve_disabled")


class CompanionIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=48)
    stance: str
    temper: str
    cloak_color: str | None = None
    keep_portrait: bool = False


class StartBody(BaseModel):
    use_living: bool = True
    size: int | None = Field(default=None, ge=1, le=3)
    companions: list[CompanionIn] = Field(default_factory=list)


class ReformBody(BaseModel):
    size: int = Field(..., ge=1, le=3)
    companions: list[CompanionIn]


class TintBody(BaseModel):
    palette_id: str = Field(..., min_length=2, max_length=16)


class PortraitBody(BaseModel):
    slot: int = Field(..., ge=1, le=3)
    name: str = Field(..., min_length=1, max_length=48)
    stance: str
    temper: str
    cloak_color: str | None = None
    retry: bool = False


@router.get("/delve/sync")
async def delve_sync(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
    tab: bool = Query(False),
):
    await _require_delve(session)
    try:
        payload = await grant_and_sync(session, player_id, mark_legacy_seen=tab)
        await session.commit()
    except DelveError as e:
        _raise(e)
        raise
    return payload


@router.post("/delve/start")
async def delve_start(
    body: StartBody,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    await _require_delve(session)
    try:
        payload = await start_delve(
            session,
            player_id,
            size=body.size,
            companions=[c.model_dump() for c in body.companions],
        )
        await session.commit()
    except DelveError as e:
        _raise(e)
        raise
    return payload


@router.post("/delve/reform")
async def delve_reform(
    body: ReformBody,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    await _require_delve(session)
    try:
        payload = await reform_delve(
            session,
            player_id,
            size=body.size,
            companions=[c.model_dump() for c in body.companions],
        )
        await session.commit()
    except DelveError as e:
        _raise(e)
        raise
    return payload


@router.post("/delve/tint")
async def delve_tint(
    body: TintBody,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    await _require_delve(session)
    try:
        payload = await tint_sleeve(session, player_id, body.palette_id)
        await session.commit()
    except DelveError as e:
        _raise(e)
        raise
    return payload


@router.get("/delve/portraits/{slot}")
async def delve_portrait(
    slot: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    await _require_delve(session)
    if slot not in (1, 2, 3):
        raise HTTPException(status_code=404, detail="invalid_slot")
    path = portrait_file(player_id, slot)
    if path.is_file():
        return FileResponse(path, media_type="image/webp")
    from waifu_bot.paths import static_game_directory

    fallback = static_game_directory() / "delve" / "templates" / "guide.webp"
    if fallback.is_file():
        return FileResponse(fallback, media_type="image/webp")
    raise HTTPException(status_code=404, detail="portrait_missing")


@router.post("/delve/portrait/generate")
async def delve_portrait_generate(
    body: PortraitBody,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    await _require_delve(session)
    try:
        result = await generate_companion_portrait(
            session,
            player_id,
            slot=body.slot,
            name=body.name,
            stance=body.stance,
            temper=body.temper,
            cloak_color=body.cloak_color,
            retry=body.retry,
        )
        await session.commit()
    except DelveError as e:
        _raise(e)
        raise
    return result


@router.post("/delve/line")
async def delve_line(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """One cheap flavor sentence. Only the open tab should call this. GET /sync never does."""
    await _require_delve(session)
    from waifu_bot.services.delve_line import request_delve_line

    try:
        payload = await request_delve_line(session, player_id)
        await session.commit()
    except DelveError as e:
        _raise(e)
        raise
    return payload
