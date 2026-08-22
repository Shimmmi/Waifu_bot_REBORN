"""Delve Progress Quest gear and consumable tables. Not main-waifu inventory."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from waifu_bot.db.base import Base


class DelveGearTemplate(Base):
    """Named base for the column shop. Flat ilvl, no affixes."""

    __tablename__ = "delve_gear_templates"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    family_key: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    slot_type: Mapped[str] = mapped_column(String(16), nullable=False)
    tier: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    base_ilvl: Mapped[int] = mapped_column(Integer, nullable=False)


class DelveCompanionGear(Base):
    """Equipped column piece on a living card."""

    __tablename__ = "delve_companion_gear"
    __table_args__ = (
        UniqueConstraint("card_id", "equipment_slot", name="uq_delve_companion_gear_slot"),
        CheckConstraint(
            "equipment_slot >= 1 AND equipment_slot <= 6",
            name="ck_delve_companion_gear_slot",
        ),
        CheckConstraint(
            "enchant_level >= 0 AND enchant_level <= 10",
            name="ck_delve_companion_gear_enchant",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    card_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companion_cards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    equipment_slot: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    template_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("delve_gear_templates.id", ondelete="SET NULL"), nullable=True
    )
    family_key: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    slot_type: Mapped[str] = mapped_column(String(16), nullable=False)
    base_ilvl: Mapped[int] = mapped_column(Integer, nullable=False)
    enchant_level: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    scaled_plus: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DelveConsumableTemplate(Base):
    """Column consumable definition."""

    __tablename__ = "delve_consumable_templates"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    effect: Mapped[str] = mapped_column(String(24), nullable=False)
    heal_frac: Mapped[int] = mapped_column(Integer, nullable=False)
    price_per_band: Mapped[int] = mapped_column(Integer, nullable=False)
    stack_cap: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    party: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)


class DelveCompanionBag(Base):
    """Per-card consumable stack."""

    __tablename__ = "delve_companion_bags"
    __table_args__ = (
        UniqueConstraint("card_id", "consumable_id", name="uq_delve_companion_bag_item"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    card_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companion_cards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    consumable_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("delve_consumable_templates.id", ondelete="CASCADE"),
        nullable=False,
    )
    qty: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
