"""Load key/value rows from `game_config`."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import GameConfig


async def get_game_config_map(session: AsyncSession) -> dict[str, str]:
    rows = (await session.execute(select(GameConfig))).scalars().all()
    return {r.key: r.value for r in rows}


def cfg_float(cfg: dict[str, str], key: str, default: float) -> float:
    try:
        return float(cfg.get(key, default))
    except (TypeError, ValueError):
        return default


def cfg_int(cfg: dict[str, str], key: str, default: int) -> int:
    try:
        return int(float(cfg.get(key, default)))
    except (TypeError, ValueError):
        return default
