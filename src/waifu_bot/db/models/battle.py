"""Battle log model."""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from waifu_bot.db.base import Base


class BattleLog(Base):
    """Battle event log."""

    __tablename__ = "battle_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.id"))
    dungeon_id: Mapped[int] = mapped_column(Integer, ForeignKey("dungeons.id"))

    # Event data
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)  # damage, skill, death, etc.
    event_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Event details

    # Battle state snapshot
    monster_hp_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monster_hp_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    player_hp_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    player_hp_after: Mapped[int | None] = mapped_column(Integer, nullable=True)

    message_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # Original message if applicable

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

