"""Tavern-related models (daily hire slots)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
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
    # Суммарный опыт уволенных наёмниц — передаётся следующей нанятой (накопительно)
    pending_hired_exp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Merc overhaul v7
    pity_legendary: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pity_epic: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    debut_legendary_done: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    merc_coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    merc_contracts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    merc_dust: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    legendary_crests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    drill_manuals: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    merc_gear_bag: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    codex_legendary_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    arena_rating: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    arena_tickets: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    arena_tickets_day: Mapped[str | None] = mapped_column(String(16), nullable=True)
    arena_attacks_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    guild_assist_day: Mapped[str | None] = mapped_column(String(16), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
