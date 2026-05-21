"""Player-to-player mail (guild members v1)."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from waifu_bot.db.base import Base


class PlayerMailStatus(StrEnum):
    UNREAD = "unread"
    READ = "read"
    CLAIMED = "claimed"


class PlayerMail(Base):
    __tablename__ = "player_mail"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sender_player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.id"), nullable=False)
    recipient_player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.id"), nullable=False)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    gold_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inventory_item_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("inventory_items.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default=PlayerMailStatus.UNREAD)
    recipient_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
