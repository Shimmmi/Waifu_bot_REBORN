"""Waifu models (main and hired)."""
from datetime import datetime
from enum import IntEnum

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    CheckConstraint,
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

    # Characteristics
    strength: Mapped[int] = mapped_column(Integer, default=10, nullable=False)  # СИЛ
    agility: Mapped[int] = mapped_column(Integer, default=10, nullable=False)  # ЛОВ
    intelligence: Mapped[int] = mapped_column(Integer, default=10, nullable=False)  # ИНТ
    endurance: Mapped[int] = mapped_column(Integer, default=10, nullable=False)  # ВЫН
    charm: Mapped[int] = mapped_column(Integer, default=10, nullable=False)  # ОБА
    luck: Mapped[int] = mapped_column(Integer, default=10, nullable=False)  # УДЧ

    # Combat stats (calculated from characteristics + equipment)
    max_hp: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    current_hp: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    # Relationships
    player: Mapped["Player"] = relationship("Player", back_populates="main_waifu")
    skills: Mapped[list["WaifuSkill"]] = relationship(
        "WaifuSkill", back_populates="waifu", cascade="all, delete-orphan"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint("level >= 1 AND level <= 50", name="check_level_range"),
        CheckConstraint("energy >= 0 AND energy <= max_energy", name="check_energy_range"),
        CheckConstraint("current_hp >= 0 AND current_hp <= max_hp", name="check_hp_range"),
    )


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

    # Characteristics
    strength: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    agility: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    intelligence: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    endurance: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    charm: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    luck: Mapped[int] = mapped_column(Integer, default=10, nullable=False)

    # Squad position (0 = reserve, 1-6 = squad slot)
    squad_position: Mapped[int | None] = mapped_column(Integer, nullable=True)

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
    )

