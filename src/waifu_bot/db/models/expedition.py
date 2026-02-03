"""Expedition models (daily slots + active runs)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Float,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from waifu_bot.db.base import Base


class ExpeditionSlot(Base):
    """A daily expedition slot (global, refreshed per Moscow day)."""

    __tablename__ = "expedition_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    slot: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..3

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    base_difficulty: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    # List of affix names/ids (placeholder; can be normalized later)
    affixes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    base_gold: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    base_experience: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("day", "slot", name="uq_expedition_slot_day"),)


class ActiveExpedition(Base):
    """A started expedition run (result fixed at start, rewards claimable after timer)."""

    __tablename__ = "active_expeditions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.id"), nullable=False)
    expedition_slot_id: Mapped[int] = mapped_column(Integer, ForeignKey("expedition_slots.id"), nullable=False)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)

    chance: Mapped[float] = mapped_column(Float, nullable=False)  # percent (0..100)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    reward_gold: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reward_experience: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    squad_waifu_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    cancelled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    claimed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notification_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    player: Mapped["Player"] = relationship("Player", lazy="joined")
    expedition_slot: Mapped["ExpeditionSlot"] = relationship("ExpeditionSlot", lazy="joined")

