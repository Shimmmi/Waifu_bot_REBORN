"""Delve column: one idle side. Gold/XP tap + theater clock."""

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


class DelveState(Base):
    """One column per player. Clock starts when t_origin is set."""

    __tablename__ = "delve_states"

    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), primary_key=True
    )
    t_origin: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_grant_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    gold_granted_total: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    xp_granted_total: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    grant_day_msk: Mapped[str | None] = mapped_column(String(16), nullable=True)
    gold_granted_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    xp_granted_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    spine_seed: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    pb_depth: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    committed_palette: Mapped[str | None] = mapped_column(String(16), nullable=True)
    pending_tint: Mapped[str | None] = mapped_column(String(16), nullable=True)
    journal_json: Mapped[list | dict | None] = mapped_column(JSONB, nullable=True)
    title_id: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    sprite_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_reform_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    legacy_names_json: Mapped[list | dict | None] = mapped_column(JSONB, nullable=True)
    migration_from_chronicle: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    legacy_seen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    former_gladiator: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    flavor_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    flavor_text: Mapped[str | None] = mapped_column(String(280), nullable=True)
    last_beat_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_beat_node: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_pq_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    run_origin: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    wipe_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pq_seed: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    pq_gold_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pq_xp_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pq_grant_day_msk: Mapped[str | None] = mapped_column(String(16), nullable=True)
    pq_last_cycle: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pq_last_d: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class DelveCompanion(Base):
    """Party of 1–3 faces on the column. No combat stats."""

    __tablename__ = "delve_companions"
    __table_args__ = (
        UniqueConstraint("player_id", "slot", name="uq_delve_companions_player_slot"),
        CheckConstraint("slot >= 1 AND slot <= 3", name="ck_delve_companion_slot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slot: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(48), nullable=False)
    stance: Mapped[str] = mapped_column(String(16), nullable=False)
    temper: Mapped[str] = mapped_column(String(16), nullable=False)
    cloak_color: Mapped[str | None] = mapped_column(String(16), nullable=True)
    image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    portrait_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    gold_earned: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    xp_earned: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    xp_unspent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    gold_wallet: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    power: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    hp_current: Mapped[int] = mapped_column(Integer, default=48, nullable=False)
    hp_max: Mapped[int] = mapped_column(Integer, default=48, nullable=False)
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
