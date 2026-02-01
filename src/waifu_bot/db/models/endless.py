"""Endless progression models (Dungeon+ and Diablo-style affix/bases)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, JSON, String, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from waifu_bot.db.base import Base


class PlayerDungeonPlus(Base):
    """Per-player unlocks for Dungeon+ levels (per dungeon)."""

    __tablename__ = "player_dungeon_plus"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.id"), nullable=False)
    dungeon_id: Mapped[int] = mapped_column(Integer, ForeignKey("dungeons.id"), nullable=False)

    unlocked_plus_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    best_completed_plus_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class ItemBase(Base):
    """Diablo-style item base with implicit bonuses and tags."""

    __tablename__ = "item_bases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    base_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name_ru: Mapped[str] = mapped_column(String(255), nullable=False)
    slot_type: Mapped[str] = mapped_column(String(32), nullable=False)
    weapon_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    attack_type: Mapped[str | None] = mapped_column(String(16), nullable=True)

    tags: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    requirements: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    implicit_effects: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    base_level_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    base_level_max: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AffixFamily(Base):
    """Affix family for Diablo-style rolling (ties together tiers/weights)."""

    __tablename__ = "affix_families"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    family_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # prefix/suffix/aspect
    exclusive_group: Mapped[str | None] = mapped_column(String(64), nullable=True)
    effect_key: Mapped[str] = mapped_column(String(64), nullable=False)

    tags_required: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tags_forbidden: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    allowed_slot_types: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    allowed_attack_types: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    weight_base: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    max_per_item: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_legendary_aspect: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    tiers: Mapped[list["AffixFamilyTier"]] = relationship(
        "AffixFamilyTier", back_populates="family", cascade="all, delete-orphan"
    )


class AffixFamilyTier(Base):
    """Tier definition within a family (min/max total level, value range, weight multiplier)."""

    __tablename__ = "affix_family_tiers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(Integer, ForeignKey("affix_families.id", ondelete="CASCADE"), nullable=False)
    affix_tier: Mapped[int] = mapped_column(Integer, nullable=False)
    min_total_level: Mapped[int] = mapped_column(Integer, nullable=False)
    max_total_level: Mapped[int] = mapped_column(Integer, nullable=False)

    # Keep numeric-ish values in DB; interpretation depends on effect_key / is_percent in InventoryAffix
    value_min: Mapped[float | None] = mapped_column(Numeric(), nullable=True)
    value_max: Mapped[float | None] = mapped_column(Numeric(), nullable=True)

    level_delta_min: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    level_delta_max: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    weight_mult: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    family: Mapped["AffixFamily"] = relationship("AffixFamily", back_populates="tiers")

