"""Google Sign-In identity validation and player linking (mobile activity client)."""
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

GOOGLE_PROVIDER = "google"
GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"


async def validate_google_id_token(id_token: str) -> dict:
    """
    Validate a Google ID token via tokeninfo endpoint.

    Returns {"sub": str, "email": str|None, "name": str|None}.
    In dev/stage/testing, X-Google-Id-Token-Dev bypass is handled by the route layer.
    """
    if not id_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="google_token_missing")

    client_id = getattr(settings, "google_client_id", None)
    if not client_id and settings.environment not in ("dev", "stage", "testing"):
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="google_auth_not_configured",
        )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(GOOGLE_TOKENINFO_URL, params={"id_token": id_token})
    except httpx.HTTPError as e:
        logger.warning("Google tokeninfo request failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="google_api_unavailable"
        ) from e

    if resp.status_code != 200:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_google_token")

    body = resp.json()
    sub = body.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_google_token")

    if client_id:
        aud = body.get("aud")
        if aud != client_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_google_audience")

    return {
        "sub": str(sub),
        "email": body.get("email"),
        "name": body.get("name") or body.get("email"),
    }


async def resolve_or_create_player_for_google(
    session: AsyncSession, google_sub: str, display_name: str | None = None
) -> int:
    """Resolve linked player or create synthetic player for Google-only account."""
    existing = (
        await session.execute(
            select(PlayerIdentityLink).where(
                PlayerIdentityLink.provider == GOOGLE_PROVIDER,
                PlayerIdentityLink.external_id == str(google_sub),
            )
        )
    ).scalar_one_or_none()
    if existing:
        return int(existing.player_id)

    try:
        seq = await session.execute(text("SELECT nextval('player_synthetic_id_seq')"))
        synth_id = int(seq.scalar_one())
        player = Player(
            id=synth_id,
            username=None,
            first_name=(display_name or "Google Player")[:64],
        )
        session.add(player)
        session.add(
            PlayerIdentityLink(
                player_id=synth_id,
                provider=GOOGLE_PROVIDER,
                external_id=str(google_sub),
                display_name=display_name,
            )
        )
        await session.commit()
        return synth_id
    except IntegrityError:
        await session.rollback()
        existing = (
            await session.execute(
                select(PlayerIdentityLink).where(
                    PlayerIdentityLink.provider == GOOGLE_PROVIDER,
                    PlayerIdentityLink.external_id == str(google_sub),
                )
            )
        ).scalar_one_or_none()
        if existing:
            return int(existing.player_id)
        raise


async def link_google_identity_to_player(
    session: AsyncSession, player_id: int, google_sub: str
) -> None:
    existing = (
        await session.execute(
            select(PlayerIdentityLink).where(
                PlayerIdentityLink.provider == GOOGLE_PROVIDER,
                PlayerIdentityLink.external_id == str(google_sub),
            )
        )
    ).scalar_one_or_none()
    if existing:
        if int(existing.player_id) != int(player_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="google_already_linked")
        return

    session.add(
        PlayerIdentityLink(
            player_id=int(player_id),
            provider=GOOGLE_PROVIDER,
            external_id=str(google_sub),
        )
    )
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="google_already_linked") from e
