"""Совершенствование (post-60 paragon): бонусы и очередь выбора."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from waifu_bot.db.base import Base


class PlayerPerfectionBonus(Base):
    """История выбранных бонусов совершенствования (для аудита и агрегатов)."""

    __tablename__ = "player_perfection_bonuses"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
    bonus_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tier_at_pick: Mapped[int] = mapped_column(Integer, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    perfection_level_gained: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class PlayerPerfectionPending(Base):
    """FIFO-очередь невыбранных офферов (обычный бонус или милстоун skill point)."""

    __tablename__ = "player_perfection_pending"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # bonus | skill_point
    perfection_level: Mapped[int] = mapped_column(Integer, nullable=False)
    offer_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
