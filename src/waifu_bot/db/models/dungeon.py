"""Dungeon and monster models."""
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


class DungeonType(IntEnum):
    """Dungeon type enum."""

    SOLO = 1
    EXPEDITION = 2
    GROUP = 3


class Dungeon(Base):
    """Dungeon template."""

    __tablename__ = "dungeons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    act: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    dungeon_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5 per act
    dungeon_type: Mapped[int] = mapped_column(Integer, nullable=False)  # DungeonType

    level: Mapped[int] = mapped_column(Integer, nullable=False)
    obstacle_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # Number of monsters

    # Rewards
    base_experience: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    base_gold: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    monsters: Mapped[list["Monster"]] = relationship(
        "Monster", back_populates="dungeon", cascade="all, delete-orphan"
    )
    progresses: Mapped[list["DungeonProgress"]] = relationship(
        "DungeonProgress", back_populates="dungeon", cascade="all, delete-orphan"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint("act >= 1 AND act <= 5", name="check_act_range"),
        CheckConstraint("dungeon_number >= 1 AND dungeon_number <= 5", name="check_dungeon_number"),
        CheckConstraint("obstacle_count >= 1", name="check_obstacle_count"),
    )


class Monster(Base):
    """Monster template."""

    __tablename__ = "monsters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dungeon_id: Mapped[int] = mapped_column(Integer, ForeignKey("dungeons.id"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    level: Mapped[int] = mapped_column(Integer, nullable=False)
    max_hp: Mapped[int] = mapped_column(Integer, nullable=False)
    damage: Mapped[int] = mapped_column(Integer, nullable=False)
    experience_reward: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    monster_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)  # Order in dungeon (1, 2, 3...)

    # Relationships
    dungeon: Mapped["Dungeon"] = relationship("Dungeon", back_populates="monsters")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class DungeonProgress(Base):
    """Player dungeon progress."""

    __tablename__ = "dungeon_progress"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.id"))
    dungeon_id: Mapped[int] = mapped_column(Integer, ForeignKey("dungeons.id"))

    # Progress state
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    current_monster_position: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    current_monster_hp: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Active battle state
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    player: Mapped["Player"] = relationship("Player", back_populates="dungeon_progresses")
    dungeon: Mapped["Dungeon"] = relationship("Dungeon", back_populates="progresses")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

