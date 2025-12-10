"""Item and inventory models."""
from datetime import datetime
from enum import IntEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from waifu_bot.db.base import Base


class ItemRarity(IntEnum):
    """Item rarity enum."""

    COMMON = 1
    UNCOMMON = 2
    RARE = 3
    EPIC = 4
    LEGENDARY = 5


class ItemType(IntEnum):
    """Item type enum."""

    WEAPON_1 = 1
    WEAPON_2 = 2
    COSTUME = 3
    RING_1 = 4
    RING_2 = 5
    AMULET = 6
    CONSUMABLE = 7
    OTHER = 8


class Item(Base):
    """Item template/model."""

    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Item properties
    rarity: Mapped[int] = mapped_column(Integer, nullable=False)  # ItemRarity
    tier: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-10 (every 5 levels)
    level: Mapped[int] = mapped_column(Integer, nullable=False)  # Item level
    item_type: Mapped[int] = mapped_column(Integer, nullable=False)  # ItemType

    # Weapon properties (if applicable)
    damage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attack_speed: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-10
    weapon_type: Mapped[str | None] = mapped_column(String(50), nullable=True)  # melee/ranged/magic
    attack_type: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Requirements
    required_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    required_strength: Mapped[int | None] = mapped_column(Integer, nullable=True)
    required_agility: Mapped[int | None] = mapped_column(Integer, nullable=True)
    required_intelligence: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Affixes/suffixes (stored as JSON)
    affixes: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {"stat": value, ...}

    # Base value for shop pricing
    base_value: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Is legendary (unique, manually created)
    is_legendary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint("tier >= 1 AND tier <= 10", name="check_tier_range"),
        CheckConstraint("level >= 1", name="check_item_level"),
    )


class InventoryItem(Base):
    """Player inventory item (instance)."""

    __tablename__ = "inventory_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.id"))
    item_id: Mapped[int] = mapped_column(Integer, ForeignKey("items.id"))

    # Equipment slot (if equipped)
    # 0 = not equipped, 1-6 = equipment slot
    equipment_slot: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    player: Mapped["Player"] = relationship("Player", back_populates="inventory_items")
    item: Mapped["Item"] = relationship("Item")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "equipment_slot IS NULL OR (equipment_slot >= 0 AND equipment_slot <= 6)",
            name="check_equipment_slot",
        ),
    )

