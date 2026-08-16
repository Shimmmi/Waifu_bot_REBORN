"""Compact JSON snapshots for TG / Mobile / Steam first-screen views."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from waifu_bot.db.base import Base


class PlayerClientSnapshot(Base):
    __tablename__ = "player_client_snapshots"

    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), primary_key=True
    )
    hub_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    inventory_summary_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    loadout_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    mercenaries_summary_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
