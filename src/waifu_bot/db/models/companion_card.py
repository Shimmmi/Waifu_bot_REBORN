"""Living mercenary cards: tavern hall + column chronicle. Not HiredWaifu."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from waifu_bot.db.base import Base


class CompanionHall(Base):
    """One hall per player: mourning, rain at the door, digest cursor."""

    __tablename__ = "companion_halls"

    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), primary_key=True
    )
    mourning_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rain_card_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("companion_cards.id", ondelete="SET NULL"), nullable=True
    )
    digest_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CompanionCard(Base):
    """A living person. Seated slot 1–3 or rain/archive."""

    __tablename__ = "companion_cards"
    __table_args__ = (
        UniqueConstraint("player_id", "slot", name="uq_companion_cards_player_slot"),
        CheckConstraint("slot IS NULL OR (slot >= 1 AND slot <= 3)", name="ck_companion_card_slot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slot: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="living")
    name: Mapped[str] = mapped_column(String(48), nullable=False)
    stance: Mapped[str] = mapped_column(String(16), nullable=False)
    temper: Mapped[str] = mapped_column(String(16), nullable=False)
    cloak_color: Mapped[str | None] = mapped_column(String(16), nullable=True)
    traits: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    look_card: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    bio: Mapped[str | None] = mapped_column(String(800), nullable=True)
    voice: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    portrait_anime_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    portrait_pixel_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    flesh: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    psyche: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    adventure_tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    relations: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    gold_earned: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    xp_earned: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    can_dismiss_beat_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    asked_to_leave: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    scar_frame: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_delve_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CompanionEvent(Base):
    """Append-only chronicle row. Mechanics already resolved."""

    __tablename__ = "companion_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
    card_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("companion_cards.id", ondelete="SET NULL"), nullable=True, index=True
    )
    beat_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    depth: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    node: Mapped[str] = mapped_column(String(16), nullable=False, default="TRAVERSE")
    template_id: Mapped[str] = mapped_column(String(48), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="mundane")
    kind: Mapped[str] = mapped_column(String(24), nullable=False, default="beat")
    line_ru: Mapped[str] = mapped_column(String(280), nullable=False, default="")
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    discovered: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    needs_prose: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    gold_delta: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    xp_delta: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
