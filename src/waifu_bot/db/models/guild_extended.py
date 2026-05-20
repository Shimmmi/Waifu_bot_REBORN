"""Guild extended mechanics: levels, skills, raids, wars."""
from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    JSON,
    UniqueConstraint,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from waifu_bot.db.base import Base


class GuildWarStatus(StrEnum):
    """Denormalized war state on guild row (quick UI)."""

    NONE = "none"
    PENDING = "pending"
    PREPARATION = "preparation"
    ACTIVE = "active"
    ENDED = "ended"


class GuildRaidStatus(StrEnum):
    PREPARATION = "preparation"
    ACTIVE = "active"
    VICTORY = "victory"
    DEFEAT = "defeat"


class GuildWarRowStatus(StrEnum):
    PENDING = "pending"
    PREPARATION = "preparation"
    ACTIVE = "active"
    ENDED = "ended"


class GuildLevelThreshold(Base):
    """Cumulative GXP required to *reach* this guild level (1..20)."""

    __tablename__ = "guild_level_thresholds"

    level: Mapped[int] = mapped_column(Integer, primary_key=True)
    gxp_required: Mapped[int] = mapped_column(Integer, nullable=False)
    member_slots: Mapped[int] = mapped_column(Integer, nullable=False)
    raid_party_slots: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    raid_tier_unlock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0 = none
    wars_unlocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    skill_tier_unlock: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class GuildSkillDefinition(Base):
    """Static guild skill templates (balance via DB)."""

    __tablename__ = "guild_skill_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    tier: Mapped[int] = mapped_column(Integer, nullable=False)
    effect_param: Mapped[str] = mapped_column(String(64), nullable=False)
    effect_per_level: Mapped[list] = mapped_column(JSON, nullable=False)  # [v1, v2, v3]
    guild_level_req: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_sp: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    cost_per_upgrade: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class GuildSkillLevelRow(Base):
    """Per-guild learned level (0 = locked) for a definition."""

    __tablename__ = "guild_skill_levels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(Integer, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False)
    skill_definition_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("guild_skill_definitions.id", ondelete="CASCADE"), nullable=False
    )
    current_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    guild: Mapped["Guild"] = relationship("Guild", back_populates="guild_skill_levels")
    definition: Mapped["GuildSkillDefinition"] = relationship("GuildSkillDefinition")

    __table_args__ = (
        UniqueConstraint("guild_id", "skill_definition_id", name="uq_guild_skill_level_guild_def"),
        CheckConstraint("current_level >= 0 AND current_level <= 3", name="ck_guild_skill_level_range"),
    )


class GuildRaidTemplate(Base):
    __tablename__ = "guild_raid_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tier: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    stages_count: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    gxp_reward: Mapped[int] = mapped_column(Integer, nullable=False)
    stage_duration_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    transition_hours_min: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    transition_hours_max: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    # Per-stage: list of {kind: trash|miniboss|final, base_hp, name_slug, affixes: []}
    stages_json: Mapped[list] = mapped_column(JSON, nullable=False)
    min_guild_level: Mapped[int] = mapped_column(Integer, nullable=False)


class GuildRaid(Base):
    __tablename__ = "guild_raids"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(Integer, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False)
    template_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("guild_raid_templates.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=GuildRaidStatus.PREPARATION.value)
    current_stage: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    phase: Mapped[str] = mapped_column(String(32), nullable=False, default="fight")  # fight | transition
    stage_monster_hp_current: Mapped[int] = mapped_column(Integer, nullable=False)
    stage_monster_hp_max: Mapped[int] = mapped_column(Integer, nullable=False)
    stage_enrage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stage_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    transition_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    gxp_reward: Mapped[int] = mapped_column(Integer, nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    pending_loot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reward_pool_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    guild: Mapped["Guild"] = relationship("Guild", back_populates="guild_raids", foreign_keys=[guild_id])
    template: Mapped["GuildRaidTemplate"] = relationship("GuildRaidTemplate")
    participants: Mapped[list["GuildRaidParticipant"]] = relationship(
        "GuildRaidParticipant", back_populates="raid", cascade="all, delete-orphan"
    )


class GuildRaidParticipant(Base):
    __tablename__ = "guild_raid_participants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    raid_id: Mapped[int] = mapped_column(Integer, ForeignKey("guild_raids.id", ondelete="CASCADE"), nullable=False)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    damage_dealt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    raid: Mapped["GuildRaid"] = relationship("GuildRaid", back_populates="participants")

    __table_args__ = (UniqueConstraint("raid_id", "player_id", name="uq_guild_raid_participant"),)


class GuildWar(Base):
    __tablename__ = "guild_wars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_a_id: Mapped[int] = mapped_column(Integer, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False)
    guild_b_id: Mapped[int] = mapped_column(Integer, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=GuildWarRowStatus.PENDING.value)
    guild_a_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    guild_b_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stake_gold: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    winner_guild_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("guilds.id", ondelete="SET NULL"), nullable=True)
    declared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    response_deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    preparation_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_narrative_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    narrative_history_json: Mapped[list | None] = mapped_column(JSON, nullable=True)


class GuildGxpBankDaily(Base):
    __tablename__ = "guild_gxp_bank_daily"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(Integer, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    gxp_from_deposits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (UniqueConstraint("guild_id", "day", name="uq_guild_gxp_bank_day"),)


class GuildWarScoreBankDaily(Base):
    """WS from bank deposits per guild per calendar day (during war)."""

    __tablename__ = "guild_war_score_bank_daily"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(Integer, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    ws_from_deposits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (UniqueConstraint("guild_id", "day", name="uq_guild_ws_bank_day"),)


class GuildActivityLog(Base):
    """Recent guild events for hall activity feed and history."""

    __tablename__ = "guild_activity_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(Integer, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_player_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    text: Mapped[str] = mapped_column(String(512), nullable=False)
    actor_avatar: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True
    )
