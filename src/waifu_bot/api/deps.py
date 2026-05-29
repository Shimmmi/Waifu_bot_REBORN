"""FastAPI dependencies."""
import logging

from fastapi import Depends, Header, HTTPException, Query, status
from sqlalchemy.exc import InvalidRequestError, OperationalError, ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.core import redis as redis_core
from waifu_bot.core.config import settings
from waifu_bot.db.session import get_session
from waifu_bot.services.auth import validate_init_data
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
    session: AsyncSession = Depends(get_db),
) -> int:
    """
    Extract player id using Telegram WebApp initData.

    Dev browser bypass: if DEV_BROWSER_TOKEN is configured, requests that supply
    X-Dev-Token matching that secret and X-Player-Id are accepted regardless of APP_ENV.
    For APP_ENV=dev only: X-Player-Id alone (without token) is also accepted.
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
