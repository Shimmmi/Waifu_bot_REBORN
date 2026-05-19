"""Guild models."""
from __future__ import annotations

from datetime import datetime

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

# GuildRaid imported for relationship foreign_keys (Guild <-> guild_raids has two FK paths:
# guild_raids.guild_id and guilds.raid_active_id).
from waifu_bot.db.models.guild_extended import GuildRaid

# Forward reference for Item
if False:  # TYPE_CHECKING
    from waifu_bot.db.models.item import Item


class Guild(Base):
    """Guild model."""

    __tablename__ = "guilds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    tag: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Guild properties (experience = GXP cumulative)
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    experience: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    gold: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    skill_points_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skill_points_spent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Optional Telegram supergroup for guild raids / activity
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Denormalized war UI (detail in guild_wars)
    war_status: Mapped[str] = mapped_column(String(32), default="none", nullable=False)
    war_opponent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("guilds.id"), nullable=True)
    war_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    war_score_enemy: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    war_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active_war_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("guild_wars.id"), nullable=True)
    war_decline_cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    raid_active_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("guild_raids.id"), nullable=True)
    trophies_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    title_badge_text: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title_badge_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # auto = split loot by contribution; manual = leader assigns in UI
    raid_loot_mode: Mapped[str] = mapped_column(String(16), default="auto", nullable=False)

    # Settings
    is_recruiting: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    min_level_requirement: Mapped[int | None] = mapped_column(Integer, nullable=True)
    required_race: Mapped[int | None] = mapped_column(Integer, nullable=True)  # WaifuRace
    required_class: Mapped[int | None] = mapped_column(Integer, nullable=True)  # WaifuClass

    # Guild icon (path or URL)
    icon_path: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Bank settings
    max_bank_items: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    withdrawal_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Per day or total

    # Relationships
    members: Mapped[list[GuildMember]] = relationship(
        "GuildMember", back_populates="guild", cascade="all, delete-orphan"
    )
    bank_items: Mapped[list["GuildBank"]] = relationship(
        "GuildBank", back_populates="guild", cascade="all, delete-orphan"
    )
    guild_skill_levels: Mapped[list[GuildSkillLevelRow]] = relationship(
        "GuildSkillLevelRow", back_populates="guild", cascade="all, delete-orphan"
    )
    # All raids of this guild (not the same as raid_active_id -> single current raid row).
    guild_raids: Mapped[list[GuildRaid]] = relationship(
        "GuildRaid",
        back_populates="guild",
        foreign_keys=[GuildRaid.guild_id],
        cascade="all, delete-orphan",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint("level >= 1", name="check_guild_level"),
        CheckConstraint("max_bank_items >= 0", name="check_max_bank_items"),
    )


class GuildMember(Base):
    """Guild member."""

    __tablename__ = "guild_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(Integer, ForeignKey("guilds.id"))
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.id"), unique=True)

    is_leader: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_officer: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    # Relationships
    guild: Mapped[Guild] = relationship("Guild", back_populates="members")
    player: Mapped["Player"] = relationship("Player", back_populates="guild_membership")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class GuildBank(Base):
    """Guild bank item."""

    __tablename__ = "guild_bank"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(Integer, ForeignKey("guilds.id"))
    item_id: Mapped[int] = mapped_column(Integer, ForeignKey("items.id"))

    # Relationships
    guild: Mapped["Guild"] = relationship("Guild", back_populates="bank_items")
    item: Mapped["Item"] = relationship("Item")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

