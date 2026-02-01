"""Dungeon and monster models."""
from datetime import datetime
from enum import IntEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Float,
    String,
    Text,
    CheckConstraint,
    JSON,
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

    # Requirements / params
    level: Mapped[int] = mapped_column(Integer, nullable=False)  # min level
    location_type: Mapped[str] = mapped_column(
        String(32), default="dungeon", nullable=False
    )  # cave/forest/ruins/etc
    difficulty: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    # Monsters count range (boss is last)
    obstacle_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # legacy/fallback
    obstacle_min: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    obstacle_max: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

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
    gold_reward: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    monster_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_boss: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    difficulty: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
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
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_monsters: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_damage_dealt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    player: Mapped["Player"] = relationship("Player", back_populates="dungeon_progresses")
    dungeon: Mapped["Dungeon"] = relationship("Dungeon", back_populates="progresses")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class MonsterTemplate(Base):
    """Monster template used for procedural dungeon generation."""

    __tablename__ = "monster_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    emoji: Mapped[str | None] = mapped_column(String(16), nullable=True)

    family: Mapped[str | None] = mapped_column(String(32), nullable=True)  # undead/beast/demon/...
    tags: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {"tags": ["cave","fire"], ...}

    act_min: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    act_max: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    level_min: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    level_max: Mapped[int] = mapped_column(Integer, default=50, nullable=False)

    weight: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    base_difficulty: Mapped[int] = mapped_column(Integer, default=10, nullable=False)

    # Simple stat curves
    hp_base: Mapped[int] = mapped_column(Integer, default=40, nullable=False)
    hp_per_level: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    dmg_base: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    dmg_per_level: Mapped[int] = mapped_column(Integer, default=2, nullable=False)

    exp_base: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    exp_per_level: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    gold_base: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    gold_per_level: Mapped[int] = mapped_column(Integer, default=2, nullable=False)

    boss_allowed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    boss_hp_mult: Mapped[float] = mapped_column(Float(), default=2.5, nullable=False)
    boss_dmg_mult: Mapped[float] = mapped_column(Float(), default=1.8, nullable=False)
    boss_reward_mult: Mapped[float] = mapped_column(Float(), default=2.0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class DungeonPool(Base):
    """Pool of monster templates for a (location_type, act, dungeon_type)."""

    __tablename__ = "dungeon_pools"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    location_type: Mapped[str] = mapped_column(String(32), nullable=False)
    act: Mapped[int] = mapped_column(Integer, nullable=False)
    dungeon_type: Mapped[int] = mapped_column(Integer, nullable=False)  # DungeonType
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    entries: Mapped[list["DungeonPoolEntry"]] = relationship(
        "DungeonPoolEntry", back_populates="pool", cascade="all, delete-orphan"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class DungeonPoolEntry(Base):
    """Entry linking a pool to a monster template with optional difficulty bounds."""

    __tablename__ = "dungeon_pool_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pool_id: Mapped[int] = mapped_column(Integer, ForeignKey("dungeon_pools.id", ondelete="CASCADE"))
    template_id: Mapped[int] = mapped_column(Integer, ForeignKey("monster_templates.id", ondelete="CASCADE"))
    weight: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    min_difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    boss_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    exclude_boss: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    pool: Mapped["DungeonPool"] = relationship("DungeonPool", back_populates="entries")


class DungeonRun(Base):
    """A single dungeon run for a player (active/completed/failed)."""

    __tablename__ = "dungeon_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.id"))
    dungeon_id: Mapped[int] = mapped_column(Integer, ForeignKey("dungeons.id"))

    # Dungeon+ (endless scaling)
    plus_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    difficulty_rating: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    drop_power_rank: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)  # active/completed/failed/abandoned
    seed: Mapped[int] = mapped_column(Integer, nullable=False)

    current_position: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    total_monsters: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    total_damage_dealt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_gold_gained: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_exp_gained: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    energy_spent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    waifu_hp_lost: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    dungeon: Mapped["Dungeon"] = relationship("Dungeon")
    monsters: Mapped[list["DungeonRunMonster"]] = relationship(
        "DungeonRunMonster", back_populates="run", cascade="all, delete-orphan"
    )


class DungeonRunMonster(Base):
    """A generated monster instance inside a run."""

    __tablename__ = "dungeon_run_monsters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("dungeon_runs.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    template_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("monster_templates.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    emoji: Mapped[str | None] = mapped_column(String(16), nullable=True)
    family: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_boss: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    level: Mapped[int] = mapped_column(Integer, nullable=False)
    difficulty: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_hp: Mapped[int] = mapped_column(Integer, nullable=False)
    current_hp: Mapped[int] = mapped_column(Integer, nullable=False)
    damage: Mapped[int] = mapped_column(Integer, nullable=False)
    exp_reward: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    gold_reward: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    run: Mapped["DungeonRun"] = relationship("DungeonRun", back_populates="monsters")


class DropRule(Base):
    """Item drop rule (boss / act / location)."""

    __tablename__ = "drop_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    act: Mapped[int] = mapped_column(Integer, nullable=False)
    boss_only: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    chance: Mapped[float] = mapped_column(Float(), default=0.05, nullable=False)
    rarity_weights: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

