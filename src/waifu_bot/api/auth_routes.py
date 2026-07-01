"""Multi-platform account linking (Steam <-> Telegram, see player_identity_links)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.api.deps import get_db, get_player_id
from waifu_bot.core.config import settings
from waifu_bot.services.auth_steam import link_steam_identity_to_player, validate_steam_ticket

router = APIRouter(prefix="/auth", tags=["auth"])


class LinkIdentityOut(BaseModel):
    ok: bool
    provider: str
    player_id: int


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
