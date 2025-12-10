"""Guild models."""
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

    # Guild properties
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    experience: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    gold: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

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
    members: Mapped[list["GuildMember"]] = relationship(
        "GuildMember", back_populates="guild", cascade="all, delete-orphan"
    )
    bank_items: Mapped[list["GuildBank"]] = relationship(
        "GuildBank", back_populates="guild", cascade="all, delete-orphan"
    )
    skills: Mapped[list["GuildSkill"]] = relationship(
        "GuildSkill", back_populates="guild", cascade="all, delete-orphan"
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
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    # Relationships
    guild: Mapped["Guild"] = relationship("Guild", back_populates="members")
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

