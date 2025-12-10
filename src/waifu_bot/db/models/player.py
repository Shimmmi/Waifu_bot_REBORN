"""Player model."""
from datetime import datetime
from enum import IntEnum

from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from waifu_bot.db.base import Base


class Player(Base):
    """Player (user) model."""

    __tablename__ = "players"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # Telegram user ID
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language_code: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Game state
    current_act: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # 1-5
    gold: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_active: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    # Relationships
    main_waifu: Mapped["MainWaifu"] = relationship(
        "MainWaifu", back_populates="player", uselist=False, cascade="all, delete-orphan"
    )
    hired_waifus: Mapped[list["HiredWaifu"]] = relationship(
        "HiredWaifu", back_populates="player", cascade="all, delete-orphan"
    )
    inventory_items: Mapped[list["InventoryItem"]] = relationship(
        "InventoryItem", back_populates="player", cascade="all, delete-orphan"
    )
    guild_membership: Mapped["GuildMember"] = relationship(
        "GuildMember", back_populates="player", uselist=False, cascade="all, delete-orphan"
    )
    dungeon_progresses: Mapped[list["DungeonProgress"]] = relationship(
        "DungeonProgress", back_populates="player", cascade="all, delete-orphan"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

