"""Guild quest system: milestones, daily, weekly."""
from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from waifu_bot.db.base import Base


class GuildQuestType(StrEnum):
    MILESTONE = "milestone"
    DAILY = "daily"
    WEEKLY = "weekly"


class GuildQuestCategory(StrEnum):
    CHAT = "chat"
    COMBAT = "combat"
    EXPEDITION = "expedition"
    ECONOMY = "economy"


class GuildQuestStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    EXPIRED = "expired"


class GuildQuestTemplate(Base):
    __tablename__ = "guild_quest_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metric: Mapped[str] = mapped_column(String(64), nullable=False)
    reset_interval: Mapped[str | None] = mapped_column(String(16), nullable=True)
    target_value: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reward_xp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    personal_reward_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class GuildQuestTier(Base):
    __tablename__ = "guild_quest_tiers"
    __table_args__ = (UniqueConstraint("template_id", "tier", name="uq_guild_quest_tiers_template_tier"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("guild_quest_templates.id", ondelete="CASCADE"), nullable=False
    )
    tier: Mapped[int] = mapped_column(Integer, nullable=False)
    target_value: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reward_xp: Mapped[int] = mapped_column(Integer, nullable=False)
    name_suffix: Mapped[str | None] = mapped_column(String(32), nullable=True)


class GuildQuest(Base):
    __tablename__ = "guild_quests"
    __table_args__ = (
        UniqueConstraint("guild_id", "template_id", "period_key", name="uq_guild_quests_guild_tpl_period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(Integer, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False)
    template_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("guild_quest_templates.id", ondelete="CASCADE"), nullable=False
    )
    tier_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("guild_quest_tiers.id", ondelete="SET NULL"), nullable=True
    )
    period_key: Mapped[str] = mapped_column(String(32), nullable=False, default="milestone")
    current_val: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    target_value: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reward_xp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=GuildQuestStatus.ACTIVE)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rewarded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GuildQuestContribution(Base):
    __tablename__ = "guild_quest_contributions"

    quest_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("guild_quests.id", ondelete="CASCADE"), primary_key=True
    )
    player_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    value: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)


class GuildWeeklyQuestBallot(Base):
    __tablename__ = "guild_weekly_quest_ballots"
    __table_args__ = (UniqueConstraint("guild_id", "week_start", name="uq_guild_weekly_ballot_guild_week"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(Integer, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    option_template_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    chosen_template_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    voted_by_player_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    voted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GuildQuestPlayerBuff(Base):
    __tablename__ = "guild_quest_player_buffs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    buff_type: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_quest_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("guild_quests.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
