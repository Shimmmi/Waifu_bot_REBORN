"""Endgame economy tables: daily challenge, temper, refine, reforge, respec."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from waifu_bot.db.base import Base


class DailyChallengeSeed(Base):
    __tablename__ = "daily_challenge_seeds"

    seed_date: Mapped[date] = mapped_column(Date, primary_key=True)
    daily_seed: Mapped[str] = mapped_column(String(64), nullable=False)
    salt_used: Mapped[str] = mapped_column(String(64), nullable=False)
    nonce_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False, server_default=text("now()")
    )


class DailyChallengeInstance(Base):
    __tablename__ = "daily_challenge_instances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    seed_date: Mapped[date] = mapped_column(
        Date, ForeignKey("daily_challenge_seeds.seed_date", ondelete="CASCADE"), nullable=False
    )
    base_dungeon_id: Mapped[int] = mapped_column(Integer, ForeignKey("dungeons.id"), nullable=False)
    act: Mapped[int] = mapped_column(Integer, nullable=False)
    tier: Mapped[int] = mapped_column(Integer, nullable=False)
    hp_mult: Mapped[float] = mapped_column(Float, nullable=False)
    dmg_mult: Mapped[float] = mapped_column(Float, nullable=False)
    gold_mult: Mapped[float] = mapped_column(Float, nullable=False)
    exp_mult: Mapped[float] = mapped_column(Float, nullable=False)
    drop_chance_bonus_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    rarity_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    affix_slots: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    gate_perfection: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    gate_ilvl: Mapped[int] = mapped_column(Integer, nullable=False, default=25)
    stipend_gold: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dust_bonus: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    core_chance: Mapped[float] = mapped_column(Float, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("seed_date", "tier", name="uq_daily_challenge_instances_date_tier"),
        CheckConstraint("tier >= 1 AND tier <= 5", name="ck_challenge_tier"),
        CheckConstraint("act >= 1 AND act <= 5", name="ck_challenge_act"),
    )


class DailyChallengeMonsterAffix(Base):
    __tablename__ = "daily_challenge_monster_affixes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("daily_challenge_instances.id", ondelete="CASCADE"), nullable=False
    )
    monster_slot_index: Mapped[int] = mapped_column(Integer, nullable=False)
    affix_id: Mapped[int] = mapped_column(Integer, ForeignKey("monster_affixes.id"), nullable=False)
    slot_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("ix_challenge_monster_affixes_instance", "instance_id", "monster_slot_index", "slot_order"),
    )


class DailyChallengeProgress(Base):
    __tablename__ = "daily_challenge_progress"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )
    instance_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("daily_challenge_instances.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="not_started")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("player_id", "instance_id", name="uq_daily_challenge_progress_player_instance"),
        CheckConstraint(
            "status IN ('not_started','active','completed','failed','abandoned')",
            name="ck_challenge_progress_status",
        ),
    )


class TemperPending(Base):
    __tablename__ = "temper_pending"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )
    inventory_item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False
    )
    affix_row_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("inventory_affixes.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    options_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    keep_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    dust_spent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gold_spent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    transaction_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index(
            "uq_temper_pending_open_item",
            "inventory_item_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
    )


class TemperTransaction(Base):
    __tablename__ = "temper_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )
    inventory_item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    dust_spent: Mapped[int] = mapped_column(Integer, nullable=False)
    gold_spent: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False, server_default=text("now()")
    )


class ReforgePending(Base):
    __tablename__ = "reforge_pending"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )
    inventory_item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    options_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    keep_bonus_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    ember_spent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gold_spent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    transaction_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index(
            "uq_reforge_pending_open_item",
            "inventory_item_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
    )


class ReforgeTransaction(Base):
    __tablename__ = "reforge_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )
    inventory_item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    ember_spent: Mapped[int] = mapped_column(Integer, nullable=False)
    gold_spent: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False, server_default=text("now()")
    )


class RefineTransaction(Base):
    __tablename__ = "refine_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )
    inventory_item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    from_grade: Mapped[int] = mapped_column(Integer, nullable=False)
    to_grade: Mapped[int] = mapped_column(Integer, nullable=False)
    cores_spent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    essence_spent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gold_spent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False, server_default=text("now()")
    )


class PerfectionRespecPending(Base):
    __tablename__ = "perfection_respec_pending"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )
    player_perfection_bonus_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("player_perfection_bonuses.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    options_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    gold_cost: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index(
            "uq_respec_pending_open_bonus",
            "player_perfection_bonus_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
    )


class PerfectionRespecDailyLock(Base):
    __tablename__ = "perfection_respec_daily_locks"

    player_perfection_bonus_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("player_perfection_bonuses.id", ondelete="CASCADE"), primary_key=True
    )
    msk_date: Mapped[date] = mapped_column(Date, primary_key=True)


class PerfectionRespecLog(Base):
    __tablename__ = "perfection_respec_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )
    old_bonus_id: Mapped[str] = mapped_column(String(64), nullable=False)
    new_bonus_id: Mapped[str] = mapped_column(String(64), nullable=False)
    gold_spent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False, server_default=text("now()")
    )


class AbyssKillMatRoll(Base):
    __tablename__ = "abyss_kill_mat_rolls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )
    session_nonce: Mapped[int] = mapped_column(Integer, nullable=False)
    floor: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint(
            "player_id", "session_nonce", "floor", name="uq_abyss_kill_mat_rolls_session_floor"
        ),
    )
