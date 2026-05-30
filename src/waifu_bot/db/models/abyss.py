"""Abyss (Бездна) infinite-dungeon models.

The Abyss is an endless vertical dungeon: the player descends floor by floor,
fighting monsters via group-chat activity. Every 10th floor is a checkpoint with
a fixed boss. Difficulty and rewards scale with depth.

Unlike solo dungeons (DungeonRun / DungeonProgress), the Abyss keeps a single
persistent progress row per player and stores the *current monster* inline as a
JSONB blob instead of generating a full table of rows ahead of time.
"""
from datetime import datetime

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


class AbyssGrace(Base):
    """Catalogue of Graces (buffs offered after a checkpoint)."""

    __tablename__ = "abyss_graces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    icon: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Effect applied to OV parameters while the Grace is active.
    # Enum: DMG_BOOST, HP_REGEN, GOLD_MULT, DODGE_BOOST, TEXT_DMG_BOOST,
    #       MEDIA_DMG_BOOST, EXP_BOOST, DMG_REDUCE, DROP_CHANCE_BOOST
    effect_type: Mapped[str] = mapped_column(String(32), nullable=False)
    effect_value: Mapped[float] = mapped_column(Float(), nullable=False)
    effect_label: Mapped[str | None] = mapped_column(String(64), nullable=True)

    min_floor: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_floor: Mapped[int | None] = mapped_column(Integer, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class AbyssCheckpointBoss(Base):
    """Fixed boss template for each checkpoint floor (not generated randomly)."""

    __tablename__ = "abyss_checkpoint_bosses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    floor_number: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)  # 10, 20, ...
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    family: Mapped[str] = mapped_column(String(32), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False)

    # Base stats (scaled by the formulas in abyss_rewards).
    base_hp: Mapped[int] = mapped_column(Integer, nullable=False)
    base_dmg: Mapped[int] = mapped_column(Integer, nullable=False)
    base_exp: Mapped[int] = mapped_column(Integer, nullable=False)

    # Special boss mechanic.
    # Enum: TANK, REFLECT, UNDYING, SPLIT, BERSERK, COMBINED, NULL
    special_mechanic: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mechanic_params: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    warning_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class AbyssProgress(Base):
    """Per-player Abyss progress (one row per player)."""

    __tablename__ = "abyss_progress"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    # Progress
    max_floor_reached: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_floor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0 = not in Abyss
    current_checkpoint: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Active session
    session_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    session_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Current monster state (inline JSON instead of an FK row). Keys:
    #   name, family, slug, level, is_boss, is_elite, elite_color,
    #   max_hp, current_hp, damage, exp_reward, gold_min, gold_max,
    #   applied_affix_ids, special_mechanic, mechanic_params, mechanic_state
    current_monster: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Active Grace (buff after a checkpoint)
    active_grace_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("abyss_graces.id"), nullable=True
    )
    grace_expires_at_floor: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Current floor modifier
    current_floor_modifier: Mapped[str | None] = mapped_column(String(32), nullable=True)
    modifier_params: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_modifier_floor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Daily limit
    checkpoints_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_checkpoint_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    # Currency
    abyss_shards: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Per-block state
    revive_scrolls_used_this_block: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    floor_monsters_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Pending Grace choices awaiting selection after a checkpoint (list of grace ids).
    pending_grace_choices: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Statistics
    total_floors_cleared: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_monsters_killed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class AbyssWeeklyLeaderboard(Base):
    """Weekly leaderboard rows (best floor reached per player per ISO week)."""

    __tablename__ = "abyss_weekly_leaderboard"
    __table_args__ = (
        UniqueConstraint("player_id", "week_start", name="uq_abyss_leaderboard_player_week"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )
    week_start: Mapped[datetime] = mapped_column(Date, nullable=False)  # Monday 00:00 MSK
    max_floor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reward_claimed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class AbyssShardsShopItem(Base):
    """Catalogue of items purchasable with Abyss Shards."""

    __tablename__ = "abyss_shards_shop"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon: Mapped[str | None] = mapped_column(String(16), nullable=True)
    item_type: Mapped[str] = mapped_column(String(32), nullable=False)  # COSMETIC/CONSUMABLE/ITEM_AFFIX/TITLE
    item_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    cost_shards: Mapped[int] = mapped_column(Integer, nullable=False)
    stock_per_week: Mapped[int | None] = mapped_column(Integer, nullable=True)  # NULL = unlimited
    min_floor_req: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
