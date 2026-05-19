"""Пассивное дерево навыков ОВ (3 ветки, узлы с уровнями)."""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from waifu_bot.db.base import Base


class PassiveSkillNode(Base):
    """Справочник узлов дерева."""

    __tablename__ = "passive_skill_nodes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    branch: Mapped[str] = mapped_column(String(16), nullable=False)  # warrior | shadow | sage
    tier: Mapped[int] = mapped_column(Integer, nullable=False)  # ряд 1..4
    position: Mapped[int] = mapped_column(Integer, nullable=False)  # позиция в ряду 1..3
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    max_level: Mapped[int] = mapped_column(Integer, nullable=False)
    waifu_level_req: Mapped[int] = mapped_column(Integer, nullable=False)
    branch_points_req: Mapped[int] = mapped_column(Integer, nullable=False)
    effect_type: Mapped[str] = mapped_column(String(64), nullable=False)
    effect_values: Mapped[list] = mapped_column(JSONB, nullable=False)
    cost_gold: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)


class PlayerPassiveSkill(Base):
    """Прогресс по узлу (уровень 0..max_level)."""

    __tablename__ = "player_passive_skills"

    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    node_id: Mapped[str] = mapped_column(String(32), ForeignKey("passive_skill_nodes.id", ondelete="CASCADE"), primary_key=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    node: Mapped["PassiveSkillNode"] = relationship("PassiveSkillNode")
