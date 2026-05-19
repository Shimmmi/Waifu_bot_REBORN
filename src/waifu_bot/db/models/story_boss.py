"""Сюжетные боссы Dungeon+ (акты × вехи +5…+30)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from waifu_bot.db.base import Base


class StoryBossDefinition(Base):
    """Определение сюжетного босса: один на пару (act, plus_tier)."""

    __tablename__ = "story_boss_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    act: Mapped[int] = mapped_column(Integer, nullable=False)  # 1–5
    plus_tier: Mapped[int] = mapped_column(Integer, nullable=False)  # 5,10,…,30
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    monster_template_id: Mapped[int] = mapped_column(Integer, ForeignKey("monster_templates.id"), nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    short_lore: Mapped[str | None] = mapped_column(Text(), nullable=True)
    intro_text: Mapped[str | None] = mapped_column(Text(), nullable=True)
    image_webp_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("act", "plus_tier", name="uq_story_boss_act_plus_tier"),
    )


class PlayerStoryBossFirstKill(Base):
    """Первое убийство сюжетного босса (для уникального счётчика)."""

    __tablename__ = "player_story_boss_first_kill"

    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    story_boss_definition_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("story_boss_definitions.id", ondelete="CASCADE"), primary_key=True
    )
    killed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    definition: Mapped["StoryBossDefinition"] = relationship("StoryBossDefinition")
