"""Expedition models (daily slots + active runs)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from waifu_bot.db.base import Base


class ExpeditionAffix(Base):
    """Аффикс экспедиции: префикс или суффикс (из ТЗ v1.1 / cursor_plan_6)."""

    __tablename__ = "expedition_affixes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)  # 'prefix' | 'suffix'
    category: Mapped[str] = mapped_column(String(32), nullable=False)  # elemental, enemy, hazard, cursed, blessed
    difficulty_add: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    damage_mult: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    reward_mult: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    paired_perks: Mapped[list | None] = mapped_column(JSON, nullable=True)
    allowed_biomes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    forbidden_biomes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    description_hint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    difficulty_tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)


class ExpeditionSlot(Base):
    """A daily expedition slot (global, refreshed per Moscow day)."""

    __tablename__ = "expedition_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    slot: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..3

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    base_difficulty: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    # Старая схема: список строковых id аффиксов (expedition_data). Новые слоты используют affix_ids.
    affixes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Новая схема (ТЗ v1.1): база + аффиксы из expedition_affixes, имя собирается детерминированно
    base_location: Mapped[str | None] = mapped_column(String(64), nullable=True)
    affix_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [int] — id из expedition_affixes
    computed_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    biome_tag: Mapped[str | None] = mapped_column(String(32), nullable=True)
    difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1 + sum(difficulty_add)
    damage_mult: Mapped[float | None] = mapped_column(Float, nullable=True)
    reward_mult: Mapped[float | None] = mapped_column(Float, nullable=True)
    paired_perks: Mapped[list | None] = mapped_column(JSON, nullable=True)  # perk ids, полезные для слота
    difficulty_tags: Mapped[list | None] = mapped_column(JSON, nullable=True)  # кэш union тегов аффиксов

    base_gold: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    base_experience: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Испытание: повышенная сложность и награда
    trial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    location_archetype_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    expedition_mode_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("day", "slot", name="uq_expedition_slot_day"),)


class ActiveExpedition(Base):
    """A started expedition run (result fixed at start, rewards claimable after timer)."""

    __tablename__ = "active_expeditions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.id"), nullable=False)
    expedition_slot_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("expedition_slots.id"), nullable=True)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)

    chance: Mapped[float] = mapped_column(Float, nullable=False)  # percent (0..100)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    reward_gold: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reward_experience: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    squad_waifu_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    cancelled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    claimed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notification_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Исход по ТЗ v1.1: success | partial_success | failure (определяется при завершении)
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # ИИ-сгенерированное описание исхода экспедиции (OpenRouter)
    event_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    player: Mapped["Player"] = relationship("Player", lazy="joined")
    expedition_slot: Mapped["ExpeditionSlot"] = relationship("ExpeditionSlot", lazy="joined")

    # --- Редизайн v1.3: конфиг без дневного слота (тип аффикса × уровень I–V × длительность) ---
    affix_level: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1..5
    affix_template_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("expedition_affixes.id", ondelete="SET NULL"), nullable=True
    )
    display_base_location: Mapped[str | None] = mapped_column(String(64), nullable=True)
    display_biome_tag: Mapped[str | None] = mapped_column(String(32), nullable=True)
    events_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    events_done: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_tick_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tick_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    difficulty_tags_snapshot: Mapped[list | None] = mapped_column(JSON, nullable=True)
    location_archetype_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    expedition_mode_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    narrative_brief: Mapped[dict | None] = mapped_column(JSON, nullable=True)

