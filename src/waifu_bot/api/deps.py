"""FastAPI dependencies."""
import logging

from fastapi import Depends, Header, HTTPException, Query, status
from sqlalchemy.exc import (
    InvalidRequestError,
    OperationalError,
    PendingRollbackError,
    ProgrammingError,
    SQLAlchemyError,
)
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.core import redis as redis_core
from waifu_bot.core.config import settings
from waifu_bot.db.session import get_session
from waifu_bot.services.auth import validate_init_data
from waifu_bot.services.auth_steam import resolve_or_create_player_for_steam, validate_steam_ticket
from waifu_bot.services.desktop_session import resolve_player_id_from_desktop_session
from waifu_bot.services.player_ban import is_player_banned

logger = logging.getLogger(__name__)


async def get_db() -> AsyncSession:
    """Provide DB session for request lifecycle."""
    try:
        async for session in get_session():
            yield session
    except ProgrammingError as e:
        # Wrong SQL, missing column/table (often: migrations not applied on server).
        logger.exception("SQLAlchemy ProgrammingError in get_db (check alembic upgrade)")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="sql_programming_error",
        ) from e
    except OperationalError as e:
        logger.exception("SQLAlchemy OperationalError in get_db (connection / DB down)")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database_unavailable",
        ) from e
    except PendingRollbackError as e:
        original = e.__cause__ or e.__context__
        if original is not None:
            logger.exception(
                "PendingRollbackError in get_db (earlier error: %s: %s)",
                type(original).__name__,
                original,
            )
        else:
            logger.exception("PendingRollbackError in get_db (session rolled back)")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="session_rollback_error",
        ) from e
    except InvalidRequestError as e:
        # Mapper/relationship misconfiguration — not a DB outage (do not return 503).
        logger.exception("SQLAlchemy InvalidRequestError in get_db (ORM mapper/relationship)")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="orm_configuration_error",
        ) from e
    except SQLAlchemyError as e:
        logger.exception("SQLAlchemy error in get_db")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database_unavailable",
        ) from e


def get_redis():
    """Provide Redis client (singleton)."""
    return redis_core.get_redis()


async def get_player_id(
    init_data: str | None = Header(None, alias="X-Telegram-Init-Data"),
    init_data_query: str | None = Query(None, alias="initData"),
    x_player_id: int | None = Header(None, alias="X-Player-Id"),
    x_dev_token: str | None = Header(None, alias="X-Dev-Token"),
    x_desktop_session: str | None = Header(None, alias="X-Desktop-Session"),
    x_steam_ticket: str | None = Header(None, alias="X-Steam-Ticket"),
    x_steam_ticket_dev: str | None = Header(None, alias="X-Steam-Ticket-Dev"),
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
) -> int:
    """
    Extract player id using Telegram WebApp initData (or Steam / desktop session).

    Dev browser bypass: if DEV_BROWSER_TOKEN is configured, requests that supply
    X-Dev-Token matching that secret and X-Player-Id are accepted regardless of APP_ENV.
    For APP_ENV=dev only: X-Player-Id alone (without token) is also accepted.

    Desktop Electron interim auth: X-Desktop-Session carries a JWT issued by
    /api/auth/desktop/* (email or Telegram OIDC) until Steamworks tickets work.

    Steam client (desktop_client/): X-Steam-Ticket carries a real Steamworks
    session ticket, validated via validate_steam_ticket() (needs
    STEAM_WEB_API_KEY/STEAM_APP_ID — Этап 6). Until Steamworks is wired up,
    X-Steam-Ticket-Dev (dev/stage/testing only) accepts a raw SteamID64 string
    so the Steam auth/link flow can be developed and tested end-to-end.
    """
    effective_init_data = init_data or init_data_query

    if effective_init_data:
        data = validate_init_data(effective_init_data, settings.bot_token)
        user = data.get("user") or {}
        user_id = user.get("id")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="user id missing in init data")
        uid = int(user_id)
        if await is_player_banned(session, uid):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="account banned")
        return uid

    if x_player_id and x_player_id > 0:
        token_ok = (
            settings.dev_browser_token
            and x_dev_token
            and x_dev_token == settings.dev_browser_token
        )
        env_ok = settings.environment == "dev"
        if token_ok or env_ok:
            if await is_player_banned(session, x_player_id):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="account banned")
            return x_player_id

    if x_desktop_session and x_desktop_session.strip():
        player_id = await resolve_player_id_from_desktop_session(redis, x_desktop_session.strip())
        if await is_player_banned(session, player_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="account banned")
        return player_id

    if x_steam_ticket:
        steam_data = await validate_steam_ticket(x_steam_ticket)
        player_id = await resolve_or_create_player_for_steam(
            session, steam_data["steamid"], steam_data.get("personaname")
        )
        if await is_player_banned(session, player_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="account banned")
        return player_id

    if x_steam_ticket_dev and settings.environment in ("dev", "stage", "testing"):
        steamid64 = x_steam_ticket_dev.strip()
        if steamid64:
            player_id = await resolve_or_create_player_for_steam(session, steamid64)
            if await is_player_banned(session, player_id):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="account banned")
            return player_id

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid Telegram init data",
    )


async def require_admin(player_id: int = Depends(get_player_id)) -> int:
    """Require that the player is an administrator."""
    if not settings.is_admin(player_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return player_id
