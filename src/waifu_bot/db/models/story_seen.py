"""Первый показ сюжетной вставки при входе в соло-данж."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from waifu_bot.db.base import Base


class PlayerDungeonStorySeen(Base):
    """Игрок уже видел сюжетную модалку для данного данжа."""

    __tablename__ = "player_dungeon_story_seen"

    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    dungeon_id: Mapped[int] = mapped_column(Integer, ForeignKey("dungeons.id", ondelete="CASCADE"), primary_key=True)
    seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
