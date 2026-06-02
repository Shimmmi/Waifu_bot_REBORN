"""Legendary unique bonus catalog."""

from datetime import datetime

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from waifu_bot.db.base import Base


class LegendaryBonus(Base):
    __tablename__ = "legendary_bonuses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bonus_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description_tpl: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_group: Mapped[str] = mapped_column(String(32), nullable=False)
    impl_complexity: Mapped[str] = mapped_column(String(8), default="medium", nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
