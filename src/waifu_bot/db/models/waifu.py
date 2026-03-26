"""Waifu models (main and hired)."""
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
    JSON,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from waifu_bot.db.base import Base


class WaifuRace(IntEnum):
    """Waifu race enum."""

    HUMAN = 1
    ELF = 2
    BEASTKIN = 3
    ANGEL = 4
    VAMPIRE = 5
    DEMON = 6
    FAIRY = 7


class WaifuClass(IntEnum):
    """Waifu class enum."""

    # Tanks
    KNIGHT = 1
    WARRIOR = 2
    # Damage
    ARCHER = 3
    MAGE = 4
    ASSASSIN = 5
    # Support
    HEALER = 6
    MERCHANT = 7


class WaifuRarity(IntEnum):
    """Waifu rarity enum."""

    COMMON = 1
    UNCOMMON = 2
    RARE = 3
    EPIC = 4
    LEGENDARY = 5


class MainWaifu(Base):
    """Main waifu (player's primary character)."""

    __tablename__ = "main_waifus"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.id"), unique=True)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    race: Mapped[int] = mapped_column(Integer, nullable=False)  # WaifuRace
    class_: Mapped[int] = mapped_column("class", Integer, nullable=False)  # WaifuClass

    # Stats
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    experience: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    energy: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    max_energy: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    energy_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    hp_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Characteristics
    strength: Mapped[int] = mapped_column(Integer, default=10, nullable=False)  # СИЛ
    agility: Mapped[int] = mapped_column(Integer, default=10, nullable=False)  # ЛОВ
    intelligence: Mapped[int] = mapped_column(Integer, default=10, nullable=False)  # ИНТ
    endurance: Mapped[int] = mapped_column(Integer, default=10, nullable=False)  # ВЫН
    charm: Mapped[int] = mapped_column(Integer, default=10, nullable=False)  # ОБА
    luck: Mapped[int] = mapped_column(Integer, default=10, nullable=False)  # УДЧ
    stat_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # Очки характеристик (ОХ)

    # Combat stats (calculated from characteristics + equipment)
    max_hp: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    current_hp: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    # Relationships
    player: Mapped["Player"] = relationship("Player", back_populates="main_waifu")
    skills: Mapped[list["WaifuSkill"]] = relationship(
        "WaifuSkill", back_populates="waifu", cascade="all, delete-orphan"
    )
    portrait_variants: Mapped[list["MainWaifuPortraitVariant"]] = relationship(
        "MainWaifuPortraitVariant",
        back_populates="main_waifu",
        cascade="all, delete-orphan",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # OpenRouter-generated portrait (main waifu creation flow)
    image_data: Mapped[str | None] = mapped_column(Text(), nullable=True)
    image_mime: Mapped[str | None] = mapped_column(String(32), nullable=True)
    image_generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint("level >= 1 AND level <= 60", name="check_level_range"),
        CheckConstraint("energy >= 0 AND energy <= max_energy", name="check_energy_range"),
        CheckConstraint("current_hp >= 0 AND current_hp <= max_hp", name="check_hp_range"),
    )


class MainWaifuPortraitDraft(Base):
    """До создания ОВ: до 3 превью портрета на игрока (генерация в вебаппе)."""

    __tablename__ = "main_waifu_portrait_drafts"
    __table_args__ = (
        UniqueConstraint("player_id", "slot_index", name="uq_mw_portrait_draft_player_slot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slot_index: Mapped[int] = mapped_column(Integer, nullable=False)
    image_data: Mapped[str] = mapped_column(Text(), nullable=False)
    image_mime: Mapped[str] = mapped_column(String(32), nullable=False, default="image/webp")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class MainWaifuPortraitVariant(Base):
    """Все сгенерированные портреты после создания ОВ (история вариантов)."""

    __tablename__ = "main_waifu_portrait_variants"
    __table_args__ = (
        UniqueConstraint("main_waifu_id", "slot_index", name="uq_mw_portrait_variant_waifu_slot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    main_waifu_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("main_waifus.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slot_index: Mapped[int] = mapped_column(Integer, nullable=False)
    image_data: Mapped[str] = mapped_column(Text(), nullable=False)
    image_mime: Mapped[str] = mapped_column(String(32), nullable=False, default="image/webp")
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    main_waifu: Mapped["MainWaifu"] = relationship("MainWaifu", back_populates="portrait_variants")


class HiredWaifu(Base):
    """Hired waifu (from tavern)."""

    __tablename__ = "hired_waifus"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.id"))

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    race: Mapped[int] = mapped_column(Integer, nullable=False)  # WaifuRace
    class_: Mapped[int] = mapped_column("class", Integer, nullable=False)  # WaifuClass
    rarity: Mapped[int] = mapped_column(Integer, nullable=False)  # WaifuRarity

    # Stats
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    experience: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Опыт в рамках текущего уровня (для лвлапа наёмниц, ТЗ v1.1)
    exp_current: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Очки улучшения перка при лвлапе (ТЗ v1.1)
    perk_upgrade_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # HP (экспедиции, лечение в таверне, реген со временем)
    max_hp: Mapped[int] = mapped_column(Integer, default=65, nullable=False)
    current_hp: Mapped[int] = mapped_column(Integer, default=65, nullable=False)
    hp_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Expedition-focused attributes
    power: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expedition_completions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    perks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    bio: Mapped[str | None] = mapped_column(Text(), nullable=True)

    # OpenRouter-generated portrait (cursor_plan_7)
    image_data: Mapped[str | None] = mapped_column(Text(), nullable=True)
    image_mime: Mapped[str | None] = mapped_column(String(32), nullable=True)
    image_generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Legacy characteristics (not used for expeditions)
    strength: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    agility: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    intelligence: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    endurance: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    charm: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    luck: Mapped[int] = mapped_column(Integer, default=10, nullable=False)

    # Squad position (0 = reserve, 1-6 = squad slot)
    squad_position: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Экспедиция v1.3: на время похода привязка к active_expedition (блок найма/продажи/второго похода)
    expedition_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("active_expeditions.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Relationships
    player: Mapped["Player"] = relationship("Player", back_populates="hired_waifus")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint("level >= 1", name="check_hired_level"),
        CheckConstraint(
            "squad_position IS NULL OR (squad_position >= 0 AND squad_position <= 6)",
            name="check_squad_position",
        ),
        CheckConstraint(
            "current_hp >= 0 AND current_hp <= max_hp", name="check_hired_hp_range"
        ),
    )
