"""Hidden skills: definitions + player progress; message counters on monsters.

Revision ID: 0035_hidden_skills
Revises: 0034_enchanting
Create Date: 2026-03-21
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0035_hidden_skills"
down_revision: Union[str, None] = "0034_enchanting"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "hidden_skill_definitions",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("icon", sa.String(length=8), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("unlock_description", sa.Text(), nullable=True),
        sa.Column("counter_type", sa.String(length=32), nullable=False),
        sa.Column("thresholds", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("effect_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("effect_values", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )

    op.create_table(
        "player_hidden_skills",
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("skill_id", sa.String(length=32), sa.ForeignKey("hidden_skill_definitions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("counter", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unlocked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_level_up", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_player_hidden_skills_player_id", "player_hidden_skills", ["player_id"])

    op.add_column(
        "dungeon_run_monsters",
        sa.Column("messages_on_monster", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("dungeon_run_monsters", "messages_on_monster", server_default=None)

    op.add_column(
        "dungeon_progress",
        sa.Column("current_monster_messages", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("dungeon_progress", "current_monster_messages", server_default=None)

    op.add_column(
        "hired_waifus",
        sa.Column("expedition_completions", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("hired_waifus", "expedition_completions", server_default=None)

    op.add_column(
        "players",
        sa.Column("perfect_dungeon_streak", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "players",
        sa.Column("no_damage_dungeon_streak", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("players", "perfect_dungeon_streak", server_default=None)
    op.alter_column("players", "no_damage_dungeon_streak", server_default=None)

    # --- Seed 27 hidden skills (26 from plan + stoic) ---
    rows = [
        (
            "chatterbox",
            "Болтун",
            "💬",
            "Активность",
            "Мастер словесного боя",
            "100 сообщений в подземельях",
            "dungeon_messages",
            [100, 1000, 2500, 5000, 10000],
            ["dmg_text_pct"],
            [2, 4, 7, 11, 16],
        ),
        (
            "early_bird",
            "Ранняя пташка",
            "🌅",
            "Активность",
            "Бонус за ранний старт",
            "Первое сообщение в подземелье после 6:00 МСК (в течение часа)",
            "early_days",
            [1, 7, 30, 90, 365],
            ["first_hit_per_hour_pct"],
            [20, 35, 55, 80, 120],
        ),
        (
            "marathon",
            "Марафонец",
            "🏃",
            "Активность",
            "Непрерывная активность",
            "6 часов подряд без пропуска",
            "marathon_runs",
            [1, 5, 15, 30, 60],
            ["hp_regen_per_active_hour"],
            [5, 12, 22, 35, 50],
        ),
        (
            "night_owl",
            "Ночная сова",
            "🦉",
            "Активность",
            "Ночной охотник",
            "Сообщения в подземелье 00:00–04:00 МСК",
            "night_messages",
            [10, 50, 150, 400, 1000],
            ["gold_night_pct"],
            [10, 20, 35, 55, 80],
        ),
        (
            "consistent",
            "Постоянство",
            "📅",
            "Активность",
            "Ежедневная активность",
            "7 дней подряд с активностью в подземелье",
            "active_days_streak",
            [7, 30, 90, 180, 365],
            ["exp_bonus_pct"],
            [3, 8, 15, 25, 40],
        ),
        (
            "speedster",
            "Молния",
            "⚡",
            "Активность",
            "Первый удар — смертельный",
            "Убить монстра за 1–3 сообщения",
            "fast_kills",
            [10, 100, 500, 2000, 5000],
            ["first_hit_crit_pct"],
            [5, 12, 22, 35, 50],
        ),
        (
            "stoic",
            "Стоик",
            "🛡️",
            "Активность",
            "Стойкость в длинном бою",
            "Убить монстра за 7+ сообщений",
            "slow_kills",
            [10, 100, 500, 2000, 5000],
            ["final_armor_pct"],
            [5, 12, 22, 35, 50],
        ),
        (
            "sticker_master",
            "Стикермастер",
            "🎭",
            "Медиа",
            "Мастер стикеров",
            "Нанести урон стикером",
            "sticker_hits",
            [50, 300, 1000, 3000, 8000],
            ["media_sticker_mult"],
            [1.0, 1.1, 1.25, 1.45, 1.7],
        ),
        (
            "photographer",
            "Фотограф",
            "📸",
            "Медиа",
            "Меткий снимок",
            "Нанести урон фото",
            "photo_hits",
            [30, 200, 700, 2000, 5000],
            ["media_photo_mult"],
            [1.3, 1.5, 1.75, 2.1, 2.6],
        ),
        (
            "audiophile",
            "Меломан",
            "🎵",
            "Медиа",
            "Боевой голос",
            "Нанести урон аудио/голосом",
            "audio_hits",
            [20, 100, 400, 1200, 3000],
            ["media_audio_mult"],
            [2.2, 2.5, 3.0, 3.7, 4.5],
        ),
        (
            "director",
            "Режиссёр",
            "🎬",
            "Медиа",
            "Кинематографический удар",
            "Нанести урон видео",
            "video_hits",
            [10, 60, 250, 800, 2000],
            ["media_video_mult"],
            [2.8, 3.3, 4.0, 5.0, 6.5],
        ),
        (
            "gif_fighter",
            "Анимист",
            "🌀",
            "Медиа",
            "Магия анимации",
            "Нанести урон GIF",
            "gif_hits",
            [25, 150, 600, 1800, 4500],
            ["media_gif_mult"],
            [1.7, 2.0, 2.5, 3.1, 4.0],
        ),
        (
            "executioner",
            "Каратель",
            "⚔️",
            "Боевые",
            "Добивание",
            "Убить монстров",
            "total_kills",
            [50, 500, 2000, 7000, 20000],
            ["finisher_dmg_pct"],
            [10, 20, 35, 55, 80],
        ),
        (
            "boss_slayer",
            "Охотник на боссов",
            "💀",
            "Боевые",
            "Гроза боссов",
            "Убить боссов",
            "boss_kills",
            [5, 25, 100, 300, 750],
            ["boss_reward_pct"],
            [10, 22, 38, 60, 90],
        ),
        (
            "elite_hunter",
            "Охотник за элитой",
            "🔵",
            "Боевые",
            "Охота на элиту",
            "Убить элитных монстров",
            "elite_kills",
            [20, 100, 400, 1200, 3000],
            ["elite_drop_pct"],
            [5, 12, 22, 35, 55],
        ),
        (
            "survivor",
            "Выживший",
            "💪",
            "Боевые",
            "Воля к жизни",
            "Получить 50%+ HP урона и выжить",
            "near_death_survivals",
            [10, 50, 200, 600, 1500],
            ["low_hp_dmg_reduce"],
            [8, 18, 30, 45, 65],
        ),
        (
            "untouchable",
            "Неприкасаемый",
            "🌬️",
            "Боевые",
            "Недосягаемый",
            "Пройти подземелья без урона по ОВ",
            "perfect_clears",
            [5, 20, 75, 200, 500],
            ["first_hits_evade_pct"],
            [10, 22, 38, 58, 85],
        ),
        (
            "dungeon_diver",
            "Исследователь",
            "🗺️",
            "Боевые",
            "Картограф данжей",
            "Пройти уникальные подземелья",
            "unique_dungeons",
            [10, 30, 60, 100, 150],
            ["first_clear_exp_pct"],
            [20, 40, 65, 100, 150],
        ),
        (
            "hoarder",
            "Скряга",
            "💰",
            "Экономика",
            "Бережливость",
            "Накопить золото без трат (серии)",
            "saving_streaks",
            [1, 5, 15, 30, 60],
            ["gold_drop_pct"],
            [5, 12, 22, 35, 52],
        ),
        (
            "merchant_friend",
            "Завсегдатай",
            "🏪",
            "Экономика",
            "Постоянный клиент",
            "Покупки в магазине",
            "shop_purchases",
            [10, 75, 300, 1000, 3000],
            ["shop_discount_pct"],
            [2, 5, 9, 14, 20],
        ),
        (
            "gambler",
            "Азартный",
            "🎲",
            "Экономика",
            "Баловень судьбы",
            "Использовать гемблу",
            "gamble_uses",
            [5, 30, 100, 300, 750],
            ["gamble_legendary_pct"],
            [1, 2.5, 5, 9, 15],
        ),
        (
            "team_player",
            "Командный игрок",
            "🤝",
            "Социальные",
            "Сила в единстве",
            "Сообщения в групповом подземелье",
            "group_messages",
            [50, 300, 1200, 4000, 10000],
            ["group_dmg_pct"],
            [5, 12, 22, 35, 52],
        ),
        (
            "expedition_veteran",
            "Ветеран экспедиций",
            "🗺️",
            "Социальные",
            "Опытный командир",
            "Завершить экспедиции",
            "completed_expeditions",
            [5, 30, 100, 300, 750],
            ["expedition_reward_pct"],
            [5, 12, 22, 35, 52],
        ),
        (
            "loyal_commander",
            "Верный командир",
            "⭐",
            "Социальные",
            "Верность",
            "Экспедиции с одной и той же наёмницей",
            "loyal_expeditions",
            [10, 50, 150, 400, 1000],
            ["loyal_unit_success_pct"],
            [3, 8, 15, 25, 40],
        ),
        (
            "perfectionist",
            "Перфекционист",
            "✨",
            "Особые",
            "Безупречность",
            "Серии подземелий без смерти ОВ",
            "perfect_series",
            [3, 20, 75, 200, 500],
            ["perfect_rarity_pct"],
            [5, 12, 22, 35, 55],
        ),
        (
            "enchanter_soul",
            "Душа кузнеца",
            "🔨",
            "Особые",
            "Мастер заточки",
            "Заточить предмет до +5 и выше",
            "items_at_5plus",
            [1, 5, 15, 30, 60],
            ["enchant_cost_pct", "enchant_chance_pct"],
            [[-5, -10, -18, -28, -40], [-5, -10, -18, -28, -40]],
        ),
        (
            "legend",
            "Легенда",
            "👑",
            "Особые",
            "Вершина мастерства",
            "Другие скрытые навыки на уровне 3+",
            "skills_at_ge3",
            [1, 2, 3, 4, 5],
            ["all_stats_pct"],
            [1, 2, 3, 5, 8],
        ),
    ]

    for r in rows:
        op.execute(
            sa.text(
                """
                INSERT INTO hidden_skill_definitions
                (id, name, icon, category, description, unlock_description, counter_type, thresholds, effect_types, effect_values)
                VALUES
                (:id, :name, :icon, :category, :description, :unlock_description, :counter_type,
                 CAST(:thresholds AS jsonb), CAST(:effect_types AS jsonb), CAST(:effect_values AS jsonb))
                """
            ).bindparams(
                id=r[0],
                name=r[1],
                icon=r[2],
                category=r[3],
                description=r[4],
                unlock_description=r[5],
                counter_type=r[6],
                thresholds=json.dumps(r[7]),
                effect_types=json.dumps(r[8]),
                effect_values=json.dumps(r[9]),
            )
        )


def downgrade() -> None:
    op.drop_index("ix_player_hidden_skills_player_id", table_name="player_hidden_skills")
    op.drop_table("player_hidden_skills")
    op.drop_table("hidden_skill_definitions")

    op.drop_column("dungeon_run_monsters", "messages_on_monster")
    op.drop_column("dungeon_progress", "current_monster_messages")
    op.drop_column("hired_waifus", "expedition_completions")
    op.drop_column("players", "perfect_dungeon_streak")
    op.drop_column("players", "no_damage_dungeon_streak")
