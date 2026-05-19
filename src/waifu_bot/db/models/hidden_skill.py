"""Hidden skills (Morrowind-style) — definitions + per-player progress."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from waifu_bot.db.base import Base


class HiddenSkillDefinition(Base):
    """Reference data for hidden skills (editable without code deploy via SQL)."""

    __tablename__ = "hidden_skill_definitions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    icon: Mapped[str | None] = mapped_column(String(8), nullable=True)
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    unlock_description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    counter_type: Mapped[str] = mapped_column(String(32), nullable=False)

    thresholds: Mapped[list] = mapped_column(JSONB, nullable=False)
    effect_types: Mapped[list] = mapped_column(JSONB, nullable=False)
    effect_values: Mapped[list] = mapped_column(JSONB, nullable=False)
    announce_in_group: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    player_rows: Mapped[list["PlayerHiddenSkill"]] = relationship(
        "PlayerHiddenSkill", back_populates="definition"
    )


class PlayerHiddenSkill(Base):
    """Player progress for a hidden skill."""

    __tablename__ = "player_hidden_skills"

    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    skill_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("hidden_skill_definitions.id", ondelete="CASCADE"), primary_key=True
    )
    counter: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unlocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_level_up: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    definition: Mapped["HiddenSkillDefinition"] = relationship(
        "HiddenSkillDefinition", back_populates="player_rows"
    )
