"""Chat activity reward accumulation (group chat)."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from waifu_bot.db.base import Base


class PlayerChatRewardWallet(Base):
    """Unclaimed gold/exp/chests from group chat activity."""

    __tablename__ = "player_chat_reward_wallets"

    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    gold: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    exp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pending_chests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_buffered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PlayerChatActivityDaily(Base):
    """Per-day chat activity stats (MSK) for caps and history."""

    __tablename__ = "player_chat_activity_daily"
    __table_args__ = (UniqueConstraint("player_id", "day", name="uq_player_chat_activity_daily_player_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    gold_earned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    exp_earned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    messages: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chests_granted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class PlayerChatActivityTotal(Base):
    """Lifetime chat activity for milestone chests."""

    __tablename__ = "player_chat_activity_totals"

    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    lifetime_points: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    chests_unlocked_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_chest_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
