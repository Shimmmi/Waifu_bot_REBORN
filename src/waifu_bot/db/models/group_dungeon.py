"""Group Dungeon (GD) models: sessions, contributions, templates, activity, events."""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column

from waifu_bot.db.base import Base


class GDDungeonTemplate(Base):
    """Template for a thematic group dungeon (5 fixed dungeons)."""

    __tablename__ = "gd_dungeon_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # HP = base_hp_from_monster * hp_multiplier (replaces base, not stacked)
    hp_multiplier: Mapped[float] = mapped_column(Float(), nullable=False)
    # Thematic bonus: e.g. "Лучники +25% урона"
    thematic_bonus_description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Which WaifuClass gets bonus (JSON array of class ids) or null = all
    thematic_bonus_class_ids: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Unique boss event key: whirlwind, tide, oasis, reflection, slowdown
    unique_event_key: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class PlayerChatFirstSeen(Base):
    """First time a player was seen in a chat (for "3 days in chat" eligibility)."""

    __tablename__ = "player_chat_first_seen"

    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.id"), primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PlayerGameAction(Base):
    """Game action in a chat (damage in GD/solo, event participation, /gd_start, /engage)."""

    __tablename__ = "player_game_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.id"), nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)  # gd_damage, gd_event, gd_start, engage
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class GDEventTemplate(Base):
    """Template for GD events (50%/10% HP, engage chain, boss unique, adaptive)."""

    __tablename__ = "gd_event_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # trigger_type: hp_50, hp_10, engage, boss_unique, adaptive
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # target_type: tank, healer, all, etc.
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(32), nullable=True)  # sticker, text, voice
    emoji_filter: Mapped[str | None] = mapped_column(String(128), nullable=True)  # fire, heal, shield
    effect_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    min_players_required: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=45, nullable=False)
    weight: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    # For boss unique: link to gd_dungeon_templates.unique_event_key
    dungeon_event_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Human-readable name
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)


class GDCompletion(Base):
    """Record of completed GD for "faster than average" reward."""

    __tablename__ = "gd_completions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    dungeon_template_id: Mapped[int] = mapped_column(Integer, ForeignKey("gd_dungeon_templates.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
