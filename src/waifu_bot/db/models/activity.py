"""Activity economy (Steam + Mobile) state and item catalog."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from waifu_bot.db.base import Base


class ActivityInputState(Base):
    """Per-player buffer of activity input units (steps/clicks = chars)."""

    __tablename__ = "activity_input_state"

    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), primary_key=True
    )
    buffer_units: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_counter: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_claim_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    units_accepted_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hits_applied_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    day_utc: Mapped[str | None] = mapped_column(String(10), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ActivityItemTemplate(Base):
    """Shared Steam/Mobile item catalog (no media affixes)."""

    __tablename__ = "activity_item_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slot_type: Mapped[str] = mapped_column(String(32), nullable=False)
    weapon_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    attack_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    attack_speed: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    damage_min: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    damage_max: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    base_stat: Mapped[str | None] = mapped_column(String(32), nullable=True)
    base_stat_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    required_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_starter: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
