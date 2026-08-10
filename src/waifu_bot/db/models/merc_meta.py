"""Merc Operations board + Arena match models."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from waifu_bot.db.base import Base


class MercOpsBoard(Base):
    __tablename__ = "merc_ops_boards"
    __table_args__ = (UniqueConstraint("player_id", "week_key", name="uq_merc_ops_board_player_week"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.id"), nullable=False)
    week_key: Mapped[str] = mapped_column(String(16), nullable=False)
    contracts_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class MercArenaMatch(Base):
    __tablename__ = "merc_arena_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    attacker_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.id"), nullable=False, index=True)
    defender_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    winner: Mapped[str] = mapped_column(String(16), nullable=False)
    rating_delta: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attacker_rating_after: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    log_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    seed: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
