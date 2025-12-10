"""Skill models."""
from datetime import datetime
from enum import IntEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from waifu_bot.db.base import Base


class SkillType(IntEnum):
    """Skill type enum."""

    ACTIVE = 1
    PASSIVE = 2


class Skill(Base):
    """Skill template."""

    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    skill_type: Mapped[int] = mapped_column(Integer, nullable=False)  # SkillType
    tier: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5

    # Active skill properties
    base_damage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    energy_cost: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cooldown: Mapped[int | None] = mapped_column(Integer, nullable=True)  # seconds

    # Passive skill properties
    stat_bonus: Mapped[str | None] = mapped_column(String(50), nullable=True)  # e.g., "strength", "hp"
    bonus_value: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Requirements
    required_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    required_skill_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("skills.id"), nullable=True
    )  # Prerequisite skill

    # Max level per act (1-5)
    max_level_act_1: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    max_level_act_2: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    max_level_act_3: Mapped[int] = mapped_column(Integer, default=9, nullable=False)
    max_level_act_4: Mapped[int] = mapped_column(Integer, default=12, nullable=False)
    max_level_act_5: Mapped[int] = mapped_column(Integer, default=15, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class WaifuSkill(Base):
    """Waifu skill (learned by main waifu)."""

    __tablename__ = "waifu_skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    waifu_id: Mapped[int] = mapped_column(Integer, ForeignKey("main_waifus.id"))
    skill_id: Mapped[int] = mapped_column(Integer, ForeignKey("skills.id"))

    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Relationships
    waifu: Mapped["MainWaifu"] = relationship("MainWaifu", back_populates="skills")
    skill: Mapped["Skill"] = relationship("Skill")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint("level >= 1", name="check_waifu_skill_level"),
    )


class GuildSkill(Base):
    """Guild skill (learned by guild)."""

    __tablename__ = "guild_skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(Integer, ForeignKey("guilds.id"))
    skill_id: Mapped[int] = mapped_column(Integer, ForeignKey("skills.id"))

    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Relationships
    guild: Mapped["Guild"] = relationship("Guild", back_populates="skills")
    skill: Mapped["Skill"] = relationship("Skill")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint("level >= 1", name="check_guild_skill_level"),
    )

