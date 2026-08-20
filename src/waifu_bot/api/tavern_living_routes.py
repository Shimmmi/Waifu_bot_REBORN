"""Living tavern API. Arena stays 410. GET /delve/sync never imports these LLM helpers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.api.deps import get_db, get_player_id
from waifu_bot.services.companion_living import (
    accept_rain,
    build_hall,
    card_history,
    card_public,
    dismiss_card,
    hire_generated,
    refuse_rain,
    rename_card,
)
from waifu_bot.services.delve import DelveError
from waifu_bot.db import models as m
from sqlalchemy import select

router = APIRouter(tags=["tavern-living"])


def _raise(err: DelveError) -> None:
    raise HTTPException(status_code=err.http_status, detail=err.code) from err


class ChatTurn(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    text: str = Field(..., min_length=1, max_length=400)


class ChatIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=400)
    history: list[ChatTurn] = Field(default_factory=list, max_length=16)


@router.get("/tavern/living/hall")
async def living_hall(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
    mark_seen: bool = Query(True),
):
    payload = await build_hall(session, player_id, mark_seen=mark_seen)
    await session.commit()
    return payload


@router.post("/tavern/living/rain/accept")
async def living_rain_accept(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    try:
        card = await accept_rain(session, player_id)
        await session.commit()
    except DelveError as e:
        _raise(e)
        raise
    return card


@router.post("/tavern/living/rain/refuse")
async def living_rain_refuse(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    await refuse_rain(session, player_id)
    await session.commit()
    return {"ok": True}


class HireIn(BaseModel):
    slot: int | None = Field(default=None, ge=1, le=3)


class RenameIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=24)


@router.post("/tavern/living/hire")
async def living_hire(
    body: HireIn,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    try:
        card = await hire_generated(session, player_id, slot=body.slot)
        await session.commit()
    except DelveError as e:
        _raise(e)
        raise
    return card


@router.get("/tavern/living/cards/{card_id}")
async def living_card(
    card_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    row = await session.get(m.CompanionCard, int(card_id))
    if row is None or int(row.player_id) != int(player_id):
        raise HTTPException(status_code=404, detail="not_found")
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    hist = await card_history(session, player_id, card_id)
    party = (
        await session.execute(
            select(m.CompanionCard).where(
                m.CompanionCard.player_id == int(player_id),
                m.CompanionCard.slot.is_not(None),
            )
        )
    ).scalars().all()
    return {**card_public(row, now=now, party=list(party)), "history": hist}


@router.post("/tavern/living/cards/{card_id}/rename")
async def living_rename(
    card_id: int,
    body: RenameIn,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    try:
        card = await rename_card(session, player_id, card_id, body.name)
        await session.commit()
    except DelveError as e:
        _raise(e)
        raise
    return card


@router.post("/tavern/living/cards/{card_id}/dismiss")
async def living_dismiss(
    card_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    try:
        await dismiss_card(session, player_id, card_id)
        await session.commit()
    except DelveError as e:
        _raise(e)
        raise
    return {"ok": True}


@router.post("/tavern/living/cards/{card_id}/chat")
async def living_chat(
    card_id: int,
    body: ChatIn,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services.companion_chat import reply_as_card

    try:
        text = await reply_as_card(
            session,
            player_id,
            card_id,
            body.text,
            history=[{"role": t.role, "text": t.text} for t in body.history],
        )
        await session.commit()
    except DelveError as e:
        _raise(e)
        raise
    row = await session.get(m.CompanionCard, int(card_id))
    left = 0
    if row is not None:
        from waifu_bot.services.companion_chat import chat_left
        from datetime import datetime, timezone

        left = chat_left(row, now=datetime.now(timezone.utc))
    return {"reply": text, "chat_left": left}


@router.post("/tavern/living/spice")
async def living_spice(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Rewrite one already-resolved special beat. Never called from GET /delve/sync."""
    from waifu_bot.services.companion_spice import spice_one

    out = await spice_one(session, player_id)
    await session.commit()
    return out or {"ok": False, "phrase": None}


@router.post("/tavern/living/art")
async def living_art(
    player_id: int = Depends(get_player_id),
):
    """Queue dual portraits + identity. Never called from GET /delve/sync."""
    from waifu_bot.services.companion_art import schedule_pending_art

    return schedule_pending_art(player_id)
