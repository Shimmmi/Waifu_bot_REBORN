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
from sqlalchemy.dialects.postgresql import ARRAY
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
    rarity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tier: Mapped[int | None] = mapped_column(Integer, nullable=True)
    level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_legendary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    damage_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    damage_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attack_speed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attack_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    weapon_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    base_stat: Mapped[str | None] = mapped_column(String(32), nullable=True)
    base_stat_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requirements: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Equipment slot (if equipped)
    # 0 = not equipped, 1-6 = equipment slot
    equipment_slot: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    player: Mapped["Player"] = relationship("Player", back_populates="inventory_items")
    item: Mapped["Item"] = relationship("Item")
    affixes: Mapped[list["InventoryAffix"]] = relationship(
        "InventoryAffix",
        back_populates="inventory_item",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "equipment_slot IS NULL OR (equipment_slot >= 0 AND equipment_slot <= 6)",
            name="check_equipment_slot",
        ),
    )


class ItemTemplate(Base):
    """Base item template (for generation)."""

    __tablename__ = "item_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slot_type: Mapped[str] = mapped_column(String(32), nullable=False)
    attack_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    weapon_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    base_tier: Mapped[int] = mapped_column(Integer, nullable=False)
    base_level: Mapped[int] = mapped_column(Integer, nullable=False)
    base_damage_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    base_damage_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    base_attack_speed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    base_stat: Mapped[str | None] = mapped_column(String(32), nullable=True)
    base_stat_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    base_rarity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    requirements: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class Affix(Base):
    """Affix/suffix definition."""

    __tablename__ = "affixes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # affix/suffix
    stat: Mapped[str] = mapped_column(String(64), nullable=False)
    value_min: Mapped[int] = mapped_column(Integer, nullable=False)
    value_max: Mapped[int] = mapped_column(Integer, nullable=False)
    is_percent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tier: Mapped[int] = mapped_column(Integer, nullable=False)
    min_level: Mapped[int] = mapped_column(Integer, nullable=False)
    applies_to: Mapped[list[str]] = mapped_column(ARRAY(String(32)), nullable=False)
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class InventoryAffix(Base):
    """Affix rolled on specific inventory item."""

    __tablename__ = "inventory_affixes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    inventory_item_id: Mapped[int] = mapped_column(Integer, ForeignKey("inventory_items.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    stat: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[str] = mapped_column(String(64), nullable=False)
    is_percent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # affix/suffix
    tier: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    inventory_item: Mapped["InventoryItem"] = relationship("InventoryItem", back_populates="affixes")


class ShopOffer(Base):
    """Daily shop offer for an act."""

    __tablename__ = "shop_offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    act: Mapped[int] = mapped_column(Integer, nullable=False)
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    inventory_item_id: Mapped[int] = mapped_column(Integer, ForeignKey("inventory_items.id", ondelete="CASCADE"))
    price_base: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    inventory_item: Mapped["InventoryItem"] = relationship("InventoryItem")

