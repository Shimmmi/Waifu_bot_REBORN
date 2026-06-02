"""Player model."""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
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
    current_act: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # 1-5, player's chosen act
    max_act: Mapped[int] = mapped_column(Integer, default=1, nullable=False)       # 1-5, highest act unlocked
    gold: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    protection_stones: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    enchant_dust: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_active: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    # Dedicated "real gameplay action" timestamp (combat hits, dungeon start).
    # Used to gate in-dungeon HP regen on being online; NOT touched by passive
    # /profile polling, so idling with the WebApp open does not count as online.
    last_combat_action_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Hidden skills: streaks updated from combat / expeditions
    perfect_dungeon_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    no_damage_dungeon_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Пассивное дерево навыков ОВ (очки за левелап вайфу)
    skill_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Секретный босс «эха» (Maven-like) после 25 соло-данжей на +30
    secret_echo_boss_unlocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    secret_echo_boss_defeated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Прогресс обучения: {version, completed: {step_id: iso_ts}, skipped, intro_reward_claimed}
    tutorial_progress: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )

    # Player profile UI (WebApp; not Telegram photo)
    avatar_preset_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avatar_custom_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    profile_showcase: Mapped[str] = mapped_column(
        String(16), default="portrait", nullable=False
    )

    # Telegram DM toggles: solo_dungeon, expedition_result, group_dungeon, raid
    dm_notification_prefs: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        server_default=(
            '{"solo_dungeon": true, "expedition_result": true, '
            '"group_dungeon": true, "raid": true}'
        ),
        nullable=False,
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

