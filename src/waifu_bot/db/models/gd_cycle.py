"""GD v1.0: cycle-based group dungeons (registration, rounds, rewards)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
    UniqueConstraint,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from waifu_bot.db.base import Base


class GDClassSkill(Base):
    __tablename__ = "gd_class_skills"
    __table_args__ = (UniqueConstraint("class_id", "media_type", name="uq_gd_class_skills_class_media"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    class_id: Mapped[str] = mapped_column(String(32), nullable=False)
    media_type: Mapped[str] = mapped_column(String(16), nullable=False)
    effect_type: Mapped[str] = mapped_column(String(32), nullable=False)
    effect_value: Mapped[float] = mapped_column(Float(), nullable=False)
    effect_duration: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    target: Mapped[str] = mapped_column(String(32), nullable=False)
    cooldown_rounds: Mapped[int] = mapped_column(Integer, default=2, nullable=False)


class GDCycle(Base):
    __tablename__ = "gd_cycles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    dungeon_template_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("gd_dungeon_templates.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), default="registration", nullable=False)
    registration_closes: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Когда закончить сбор действий для текущего раунда (UTC). NULL = между тиками / не активен.
    round_deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_rounds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_round_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    battle_state_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    registrations: Mapped[list["GDRegistration"]] = relationship(
        "GDRegistration", back_populates="cycle", cascade="all, delete-orphan"
    )


class GDRegistration(Base):
    __tablename__ = "gd_registrations"
    __table_args__ = (UniqueConstraint("cycle_id", "user_id", name="uq_gd_reg_cycle_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cycle_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("gd_cycles.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    waifu_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    # collecting_for_round at join time (1 = full registration; >1 = late join)
    joined_at_round: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    cycle: Mapped["GDCycle"] = relationship("GDCycle", back_populates="registrations")


class GDRound(Base):
    __tablename__ = "gd_rounds"
    __table_args__ = (
        CheckConstraint(
            "round_outcome IN ('victory','ongoing','party_wiped')",
            name="ck_gd_rounds_round_outcome",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cycle_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("gd_cycles.id", ondelete="CASCADE"), nullable=False
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    monsters_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    actions_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    outcomes_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    context_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    round_outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    ai_narrative: Mapped[str | None] = mapped_column(Text, nullable=True)
    telegram_msg_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class GDActiveEffect(Base):
    __tablename__ = "gd_active_effects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cycle_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("gd_cycles.id", ondelete="CASCADE"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(String(8), nullable=False)
    target_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    effect_type: Mapped[str] = mapped_column(String(32), nullable=False)
    effect_value: Mapped[float] = mapped_column(Float(), nullable=False)
    expires_round: Mapped[int] = mapped_column(Integer, nullable=False)
    # Round when the effect was applied (DoT/regen skip tick on the same round).
    applied_round: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class GDSkillCooldown(Base):
    __tablename__ = "gd_skill_cooldowns"

    cycle_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("gd_cycles.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    media_type: Mapped[str] = mapped_column(String(16), primary_key=True)
    available_from_round: Mapped[int] = mapped_column(Integer, nullable=False)


class GDRewardRow(Base):
    __tablename__ = "gd_rewards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cycle_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("gd_cycles.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    exp_earned: Mapped[int] = mapped_column(Integer, nullable=False)
    gold_earned: Mapped[int] = mapped_column(Integer, nullable=False)
    items_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    contribution_pct: Mapped[float] = mapped_column(Float(), nullable=False)
    dm_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
