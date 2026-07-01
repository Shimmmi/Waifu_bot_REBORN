"""Personal gamble mystery offers per player/act."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from waifu_bot.db.base import Base


class GambleOffer(Base):
    """Daily personal gamble slots (12 mystery items per player per act)."""

    __tablename__ = "gamble_offers"
    __table_args__ = (
        UniqueConstraint("player_id", "act", "slot", name="uq_gamble_offers_player_act_slot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.id", ondelete="CASCADE"), index=True)
    act: Mapped[int] = mapped_column(Integer, nullable=False)
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    inventory_item_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("inventory_items.id", ondelete="SET NULL"), nullable=True
    )
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    purchased: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    refreshed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    inventory_item: Mapped["InventoryItem"] = relationship("InventoryItem")
