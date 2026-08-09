"""Multi-platform account linking (Steam / Google <-> Telegram)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.api.deps import get_db, get_player_id, get_redis
from waifu_bot.core.config import settings
from waifu_bot.services.activity_starter import ensure_activity_starter_gear
from waifu_bot.services.auth_google import (
    link_google_identity_to_player,
    resolve_or_create_player_for_google,
    validate_google_id_token,
)
from waifu_bot.services.auth_steam import link_steam_identity_to_player, validate_steam_ticket
from waifu_bot.services.desktop_session import (
    create_desktop_session_token,
    store_desktop_session_jti,
)
from waifu_bot.services.link_code import consume_link_code, issue_link_code

router = APIRouter(prefix="/auth", tags=["auth"])


class LinkIdentityOut(BaseModel):
    ok: bool
    provider: str
    player_id: int


class LinkCodeOut(BaseModel):
    code: str
    ttl_seconds: int = 600


class GoogleLoginIn(BaseModel):
    id_token: str | None = None
    # Dev/stage only: raw google sub string when GOOGLE_CLIENT_ID not set
    google_sub_dev: str | None = None
    link_code: str | None = Field(
        None, description="Optional Telegram link code to bind Google to existing player"
    )


class GoogleLoginOut(BaseModel):
    ok: bool
    player_id: int
    desktop_session: str
    linked: bool = False


@router.post("/link_identity/steam", response_model=LinkIdentityOut)
async def link_steam_identity(
    x_steam_ticket: str | None = Header(None, alias="X-Steam-Ticket"),
    x_steam_ticket_dev: str | None = Header(None, alias="X-Steam-Ticket-Dev"),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """
    Link the caller's Steam account to their currently-authenticated player
    (typically a Telegram player_id, resolved via the normal X-Telegram-Init-Data
    header on this same request). Idempotent; 409 if that Steam account is
    already linked to a *different* player.
    """
    if x_steam_ticket:
        steam_data = await validate_steam_ticket(x_steam_ticket)
        steamid64 = steam_data["steamid"]
        persona_name = steam_data.get("personaname")
    elif x_steam_ticket_dev and settings.environment in ("dev", "stage", "testing"):
        steamid64 = x_steam_ticket_dev.strip()
        persona_name = None
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="steam_ticket_missing")

    if not steamid64:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="steam_ticket_missing")

    await link_steam_identity_to_player(session, player_id, steamid64, persona_name)
    return LinkIdentityOut(ok=True, provider="steam", player_id=player_id)


@router.post("/link_code", response_model=LinkCodeOut)
async def create_link_code(
    player_id: int = Depends(get_player_id),
    redis=Depends(get_redis),
):
    """Issue a one-time code for linking Steam/Mobile to this Telegram player."""
    code = await issue_link_code(redis, player_id)
    return LinkCodeOut(code=code, ttl_seconds=600)


@router.post("/mobile/google", response_model=GoogleLoginOut)
async def mobile_google_login(
    body: GoogleLoginIn,
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """
    Mobile Google Sign-In → desktop-session JWT.
    Optional link_code binds Google identity to an existing Telegram player.
    """
    linked = False
    if body.id_token:
        google = await validate_google_id_token(body.id_token)
        google_sub = google["sub"]
        display_name = google.get("name")
    elif body.google_sub_dev and settings.environment in ("dev", "stage", "testing"):
        google_sub = body.google_sub_dev.strip()
        display_name = "Google Dev"
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="google_token_missing")

    if body.link_code:
        target_player_id = await consume_link_code(redis, body.link_code)
        await link_google_identity_to_player(session, target_player_id, google_sub)
        player_id = target_player_id
        linked = True
    else:
        player_id = await resolve_or_create_player_for_google(session, google_sub, display_name)

    await ensure_activity_starter_gear(session, player_id)
    await session.commit()

    token, jti = create_desktop_session_token(player_id, auth_provider="google")
    await store_desktop_session_jti(redis, player_id, jti)
    return GoogleLoginOut(
        ok=True, player_id=player_id, desktop_session=token, linked=linked
    )


@router.post("/link_identity/google", response_model=LinkIdentityOut)
async def link_google_identity(
    body: GoogleLoginIn,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Link Google to the currently authenticated player (e.g. Telegram WebApp)."""
    if body.id_token:
        google = await validate_google_id_token(body.id_token)
        google_sub = google["sub"]
    elif body.google_sub_dev and settings.environment in ("dev", "stage", "testing"):
        google_sub = body.google_sub_dev.strip()
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="google_token_missing")

    await link_google_identity_to_player(session, player_id, google_sub)
    return LinkIdentityOut(ok=True, provider="google", player_id=player_id)
