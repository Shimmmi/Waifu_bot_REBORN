"""Key/value game configuration (tunable balance)."""
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from waifu_bot.db.base import Base


class GameConfig(Base):
    """Single-row-per-key configuration (e.g. enchant ratios)."""

    __tablename__ = "game_config"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
