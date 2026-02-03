"""Tavern-related models (daily hire slots)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from waifu_bot.db.base import Base


class TavernHireSlot(Base):
    """
    Daily hire slot for tavern.

    A player has up to 4 slots per Moscow day. Each slot can be consumed once.
    """

    __tablename__ = "tavern_hire_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.id"), nullable=False)

    # Moscow-day key (date in Europe/Moscow)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    slot: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..4

    hired_waifu_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("hired_waifus.id"), nullable=True)
    hired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    player: Mapped["Player"] = relationship("Player", lazy="joined")
    hired_waifu: Mapped["HiredWaifu | None"] = relationship("HiredWaifu", lazy="joined")

    __table_args__ = (
        UniqueConstraint("player_id", "day", "slot", name="uq_tavern_hire_slot_day"),
        CheckConstraint("slot >= 1 AND slot <= 4", name="check_tavern_hire_slot_range"),
    )


class TavernState(Base):
    """Global tavern progression per player."""

    __tablename__ = "tavern_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.id"), unique=True)

    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    experience: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    daily_experience: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_exp_day: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
