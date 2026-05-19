"""Item art (images) registry.

Stores mapping from (art_key, tier) -> relative web asset path.
Used by WebApp to display tiered .webp images per item type.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from waifu_bot.db.base import Base


class ItemArt(Base):
    __tablename__ = "item_art"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # e.g. weapon_sword_1h/foo or legacy flat weapon_sword_1h
    art_key: Mapped[str] = mapped_column(String(191), nullable=False)
    tier: Mapped[int] = mapped_column(Integer, nullable=False)

    # Path relative to static/game (URL /static/game/...), often "items_webp/..." in DB
    relative_path: Mapped[str] = mapped_column(String(255), nullable=False)
    mime: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'image/webp'"))

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("tier >= 1 AND tier <= 10", name="check_item_art_tier_range"),
        UniqueConstraint("art_key", "tier", name="uq_item_art_key_tier"),
    )

