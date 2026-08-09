"""Steam identity validation and player linking/resolution.

Real Steamworks integration lands in Этап 6 (requires a paid Steamworks
Partner account, see plan §1.3/§3). Until then ``validate_steam_ticket``
is a scaffold that talks to the real Steamworks Web API when a key is
configured, and otherwise fails closed with 501 so the dev-only header
stub (X-Steam-Ticket-Dev, see api/deps.py) is the only way to exercise
this code path in dev/stage.
"""
from __future__ import annotations

import logging

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.core.config import settings
from waifu_bot.db.models.player import Player
from waifu_bot.db.models.player_identity_link import PlayerIdentityLink

logger = logging.getLogger(__name__)

STEAM_PROVIDER = "steam"

STEAM_AUTH_TICKET_URL = "https://partner.steam-api.com/ISteamUserAuth/AuthenticateUserTicket/v1/"


async def validate_steam_ticket(ticket: str) -> dict:
    """
    Validate a Steam session ticket via the Steamworks Web API.

    Returns a dict with at least {"steamid": "<SteamID64 as str>", "personaname": str|None}.
    Raises HTTPException on failure.

    NOTE: this calls the real Steamworks Web API and requires STEAM_WEB_API_KEY +
    STEAM_APP_ID to be configured (Этап 6 — Steamworks Partner account). Until then
    it fails closed with 501, by design: silently trusting an unverified ticket would
    let anyone claim any SteamID64.
    """
    if not ticket:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="steam_ticket_missing")

    if not settings.steam_web_api_key or not settings.steam_app_id:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="steam_auth_not_configured",
        )

    params = {
        "key": settings.steam_web_api_key,
        "appid": settings.steam_app_id,
        "ticket": ticket,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(STEAM_AUTH_TICKET_URL, params=params)
    except httpx.HTTPError as e:
        logger.warning("Steam ticket validation request failed: %s", e)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="steam_api_unavailable") from e

    if resp.status_code != 200:
        logger.warning("Steam ticket validation HTTP %s: %s", resp.status_code, resp.text[:500])
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_steam_ticket")

    body = resp.json().get("response", {})
    params_out = body.get("params")
    if not params_out or params_out.get("result") != "OK":
        error = body.get("error", {})
        logger.warning("Steam ticket rejected: %s", error)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_steam_ticket")

    steamid = params_out.get("steamid")
    if not steamid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_steam_ticket")

    return {"steamid": str(steamid), "personaname": None}


async def resolve_or_create_player_for_steam(
    session: AsyncSession, steamid64: str, persona_name: str | None = None
) -> int:
    """
    Resolve an existing player_id linked to this SteamID64, or create a new
    Steam-native Player (synthetic negative id) if this is the first time
    this SteamID64 has ever been seen.

    Idempotent: calling this repeatedly for the same steamid64 always returns
    the same player_id.

    Concurrency note: the desktop client fires several authenticated requests
    in quick succession on first launch (e.g. /api/profile and the input
    tracker's /api/pc/hits/batch flush both within the first few seconds),
    so two requests can race to create the *same* steamid64's row before
    either commits. The UniqueConstraint on (provider, external_id) is the
    source of truth for "first one wins"; the loser rolls back and re-reads
    the winner's row instead of surfacing a 500.
    """
    link = await session.scalar(
        select(PlayerIdentityLink).where(
            PlayerIdentityLink.provider == STEAM_PROVIDER,
            PlayerIdentityLink.external_id == steamid64,
        )
    )
    if link is not None:
        return link.player_id

    new_id_row = await session.execute(text("SELECT nextval('player_synthetic_id_seq')"))
    new_id = int(new_id_row.scalar_one())

    player = Player(id=new_id, username=None, first_name=persona_name or "Steam Player")
    session.add(player)
    session.add(
        PlayerIdentityLink(
            player_id=new_id,
            provider=STEAM_PROVIDER,
            external_id=steamid64,
            display_name=persona_name,
        )
    )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        link = await session.scalar(
            select(PlayerIdentityLink).where(
                PlayerIdentityLink.provider == STEAM_PROVIDER,
                PlayerIdentityLink.external_id == steamid64,
            )
        )
        if link is not None:
            return link.player_id
        raise
    logger.info("Created Steam-native player id=%s for steamid64=%s", new_id, steamid64)
    return new_id


async def link_steam_identity_to_player(
    session: AsyncSession, player_id: int, steamid64: str, persona_name: str | None = None
) -> None:
    """
    Link a SteamID64 to an *existing* (already-authenticated, e.g. Telegram) player.

    Raises 409 if that SteamID64 is already linked to a different player_id
    (merging two independent progress histories is a manual/support operation,
    not handled automatically here).
    """
    existing = await session.scalar(
        select(PlayerIdentityLink).where(
            PlayerIdentityLink.provider == STEAM_PROVIDER,
            PlayerIdentityLink.external_id == steamid64,
        )
    )
    if existing is not None:
        if existing.player_id == player_id:
            return  # already linked, idempotent no-op
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="steam_account_already_linked_to_another_player",
        )

    session.add(
        PlayerIdentityLink(
            player_id=player_id,
            provider=STEAM_PROVIDER,
            external_id=steamid64,
            display_name=persona_name,
        )
    )
    await session.commit()
