"""Guild quest system tables and seed templates.

Revision ID: 0098_guild_quests
Revises: 0097_main_waifu_paperdoll_bonus_generations
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0098_guild_quests"
down_revision: Union[str, None] = "0097_main_waifu_paperdoll_bonus_generations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PERSONAL_DAILY = json.dumps({"exp_pct": 5, "hours": 24})
PERSONAL_WEEKLY = json.dumps({"exp_pct": 8, "hours": 48})
PERSONAL_MILESTONE = json.dumps({"exp_pct": 10, "hours": 24})

MILESTONE_SEEDS = [
    ("chat", "Стикер-марафон", "Участники гильдии отправляют стикеры в групповых чатах.", "stickers_sent", [
        (1, 100, 50, " I"), (2, 1000, 200, " II"), (3, 10000, 500, " III"),
        (4, 50000, 1000, " IV"), (5, 100000, 2000, " V"),
    ]),
    ("chat", "Голос гильдии", "Аудиосообщения в групповых чатах.", "audio_messages_sent", [
        (1, 100, 120, " I"), (2, 500, 400, " II"), (3, 2000, 1000, " III"),
    ]),
    ("chat", "Видеопоток", "Видеосообщения в групповых чатах.", "videos_sent", [
        (1, 50, 100, " I"), (2, 300, 350, " II"), (3, 1500, 900, " III"),
    ]),
    ("chat", "Гиф-армия", "GIF-анимации в групповых чатах.", "gifs_sent", [
        (1, 200, 60, " I"), (2, 2000, 250, " II"), (3, 20000, 800, " III"), (4, 80000, 1800, " IV"),
    ]),
    ("chat", "Тысяча слов", "Текстовые сообщения в групповых чатах.", "text_messages_sent", [
        (1, 1000, 40, " I"), (2, 10000, 150, " II"), (3, 100000, 400, " III"),
        (4, 500000, 900, " IV"), (5, 2000000, 2200, " V"),
    ]),
    ("combat", "Истребители монстров", "Суммарное количество убитых монстров.", "monsters_killed", [
        (1, 500, 80, " I"), (2, 2000, 250, " II"), (3, 8000, 600, " III"),
        (4, 25000, 1200, " IV"), (5, 100000, 3000, " V"),
    ]),
    ("combat", "Охотники на боссов", "Убитые боссы всеми участниками.", "bosses_killed", [
        (1, 20, 150, " I"), (2, 100, 450, " II"), (3, 500, 1200, " III"), (4, 2000, 3500, " IV"),
    ]),
    ("combat", "Элитная бригада", "Убитые элитные монстры.", "elites_killed", [
        (1, 50, 200, " I"), (2, 500, 700, " II"), (3, 5000, 2500, " III"),
    ]),
    ("combat", "Суммарный урон", "Суммарный урон по монстрам.", "total_damage_dealt", [
        (1, 100_000, 60, " I"), (2, 1_000_000, 200, " II"), (3, 10_000_000, 600, " III"),
        (4, 100_000_000, 1800, " IV"), (5, 1_000_000_000, 5000, " V"),
    ]),
    ("combat", "Критический отряд", "Критические удары в бою.", "critical_hits", [
        (1, 500, 100, " I"), (2, 5000, 400, " II"), (3, 50000, 1500, " III"),
    ]),
    ("expedition", "Экспедиционный корпус", "Успешно завершённые экспедиции.", "expeditions_completed", [
        (1, 10, 80, " I"), (2, 50, 300, " II"), (3, 200, 900, " III"), (4, 1000, 2800, " IV"),
    ]),
    ("expedition", "Без потерь", "Экспедиции без потерь наёмниц.", "expeditions_no_death", [
        (1, 10, 120, " I"), (2, 50, 450, " II"), (3, 200, 1400, " III"),
    ]),
    ("expedition", "Долгий поход", "Суммарное время в экспедициях (минуты).", "expedition_minutes", [
        (1, 300, 100, " I"), (2, 3000, 500, " II"), (3, 30000, 2000, " III"),
    ]),
    ("economy", "Золотой фонд", "Заработанное золото участниками.", "gold_earned", [
        (1, 10_000, 50, " I"), (2, 100_000, 200, " II"), (3, 1_000_000, 700, " III"), (4, 10_000_000, 2500, " IV"),
    ]),
    ("economy", "Коллекционеры", "Найденные предметы.", "items_found", [
        (1, 100, 70, " I"), (2, 1000, 280, " II"), (3, 10000, 1100, " III"),
    ]),
    ("economy", "Редкие вещи", "Предметы редкости Rare и выше.", "rare_items_found", [
        (1, 50, 100, " I"), (2, 500, 450, " II"), (3, 5000, 1800, " III"),
    ]),
]

DAILY_SEEDS = [
    ("chat", "Стикерный день", "Отправьте стикеры в групповом чате.", "stickers_sent", 50, 15),
    ("chat", "Беседа", "Текстовые сообщения в чате.", "text_messages_sent", 200, 10),
    ("chat", "Гиф-день", "GIF в групповом чате.", "gifs_sent", 20, 12),
    ("chat", "Голос дня", "Аудиосообщения в чате.", "audio_messages_sent", 10, 25),
    ("combat", "Охота дня", "Убейте монстров.", "monsters_killed", 30, 20),
    ("combat", "Урон дня", "Нанесите урон монстрам.", "total_damage_dealt", 50_000, 25),
    ("combat", "Криты дня", "Нанесите критические удары.", "critical_hits", 50, 20),
    ("combat", "Боссы дня", "Убейте боссов.", "bosses_killed", 3, 40),
    ("expedition", "Поход дня", "Завершите экспедицию.", "expeditions_completed", 1, 30),
    ("economy", "Золото дня", "Заработайте золото.", "gold_earned", 5000, 15),
    ("economy", "Находки дня", "Найдите предметы.", "items_found", 10, 15),
    ("chat", "Видео дня", "Видеосообщения в чате.", "videos_sent", 5, 20),
]

WEEKLY_SEEDS = [
    ("combat", "Элитная неделя", "Убейте элитных монстров за неделю.", "elites_killed", 20, 300),
    ("chat", "Видеонеделя", "Видеосообщения за неделю.", "videos_sent", 50, 250),
    ("combat", "Истребление", "Убейте монстров за неделю.", "monsters_killed", 500, 400),
    ("combat", "Штурм урона", "Нанесите урон за неделю.", "total_damage_dealt", 2_000_000, 500),
    ("expedition", "Экспедиционная неделя", "Завершите экспедиции.", "expeditions_completed", 15, 350),
    ("economy", "Золотая неделя", "Заработайте золото.", "gold_earned", 500_000, 300),
    ("economy", "Редкие находки", "Найдите редкие предметы.", "rare_items_found", 30, 400),
    ("chat", "Стикерная неделя", "Стикеры за неделю.", "stickers_sent", 2000, 200),
    ("expedition", "Длинные походы", "Время в экспедициях (мин).", "expedition_minutes", 6000, 450),
]


def upgrade() -> None:
    op.create_table(
        "guild_quest_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metric", sa.String(64), nullable=False),
        sa.Column("reset_interval", sa.String(16), nullable=True),
        sa.Column("target_value", sa.BigInteger(), nullable=True),
        sa.Column("reward_xp", sa.Integer(), nullable=True),
        sa.Column("personal_reward_json", JSONB(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_guild_quest_templates_metric", "guild_quest_templates", ["metric"])
    op.create_index("ix_guild_quest_templates_type", "guild_quest_templates", ["type"])

    op.create_table(
        "guild_quest_tiers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("tier", sa.Integer(), nullable=False),
        sa.Column("target_value", sa.BigInteger(), nullable=False),
        sa.Column("reward_xp", sa.Integer(), nullable=False),
        sa.Column("name_suffix", sa.String(32), nullable=True),
        sa.ForeignKeyConstraint(["template_id"], ["guild_quest_templates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_id", "tier", name="uq_guild_quest_tiers_template_tier"),
    )

    op.create_table(
        "guild_quests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guild_id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("tier_id", sa.Integer(), nullable=True),
        sa.Column("period_key", sa.String(32), nullable=False, server_default="milestone"),
        sa.Column("current_val", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("target_value", sa.BigInteger(), nullable=True),
        sa.Column("reward_xp", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rewarded", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["guild_id"], ["guilds.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["guild_quest_templates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tier_id"], ["guild_quest_tiers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("guild_id", "template_id", "period_key", name="uq_guild_quests_guild_tpl_period"),
    )
    op.create_index("ix_guild_quests_guild_status", "guild_quests", ["guild_id", "status"])

    op.create_table(
        "guild_quest_contributions",
        sa.Column("quest_id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("value", sa.BigInteger(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["quest_id"], ["guild_quests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("quest_id", "player_id"),
    )

    op.create_table(
        "guild_weekly_quest_ballots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guild_id", sa.Integer(), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("option_template_ids", JSONB(), nullable=False),
        sa.Column("chosen_template_id", sa.Integer(), nullable=True),
        sa.Column("voted_by_player_id", sa.BigInteger(), nullable=True),
        sa.Column("voted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["guild_id"], ["guilds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("guild_id", "week_start", name="uq_guild_weekly_ballot_guild_week"),
    )

    op.create_table(
        "guild_quest_player_buffs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("buff_type", sa.String(32), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_quest_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["source_quest_id"], ["guild_quests.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_guild_quest_player_buffs_player", "guild_quest_player_buffs", ["player_id"])

    conn = op.get_bind()
    sort = 0
    for cat, name, desc, metric, tiers in MILESTONE_SEEDS:
        sort += 1
        row = conn.execute(
            sa.text(
                "INSERT INTO guild_quest_templates "
                "(type, category, name, description, metric, reset_interval, personal_reward_json, sort_order) "
                "VALUES ('milestone', :cat, :name, :desc, :metric, NULL, CAST(:pr AS jsonb), :sort) "
                "RETURNING id"
            ),
            {"cat": cat, "name": name, "desc": desc, "metric": metric, "pr": PERSONAL_MILESTONE, "sort": sort},
        ).fetchone()
        tpl_id = int(row[0])
        for tier_n, target, xp, suffix in tiers:
            conn.execute(
                sa.text(
                    "INSERT INTO guild_quest_tiers (template_id, tier, target_value, reward_xp, name_suffix) "
                    "VALUES (:tid, :tier, :target, :xp, :suffix)"
                ),
                {"tid": tpl_id, "tier": tier_n, "target": target, "xp": xp, "suffix": suffix},
            )

    for cat, name, desc, metric, target, xp in DAILY_SEEDS:
        sort += 1
        conn.execute(
            sa.text(
                "INSERT INTO guild_quest_templates "
                "(type, category, name, description, metric, reset_interval, target_value, reward_xp, "
                "personal_reward_json, sort_order) "
                "VALUES ('daily', :cat, :name, :desc, :metric, 'daily', :target, :xp, CAST(:pr AS jsonb), :sort)"
            ),
            {
                "cat": cat,
                "name": name,
                "desc": desc,
                "metric": metric,
                "target": target,
                "xp": xp,
                "pr": PERSONAL_DAILY,
                "sort": sort,
            },
        )

    for cat, name, desc, metric, target, xp in WEEKLY_SEEDS:
        sort += 1
        conn.execute(
            sa.text(
                "INSERT INTO guild_quest_templates "
                "(type, category, name, description, metric, reset_interval, target_value, reward_xp, "
                "personal_reward_json, sort_order) "
                "VALUES ('weekly', :cat, :name, :desc, :metric, 'weekly', :target, :xp, CAST(:pr AS jsonb), :sort)"
            ),
            {
                "cat": cat,
                "name": name,
                "desc": desc,
                "metric": metric,
                "target": target,
                "xp": xp,
                "pr": PERSONAL_WEEKLY,
                "sort": sort,
            },
        )

    # Backfill milestone quests for existing guilds
    conn.execute(
        sa.text(
            """
            INSERT INTO guild_quests (guild_id, template_id, tier_id, period_key, created_at)
            SELECT g.id, t.id, (
                SELECT qt.id FROM guild_quest_tiers qt
                WHERE qt.template_id = t.id ORDER BY qt.tier ASC LIMIT 1
            ), 'milestone', now()
            FROM guilds g
            CROSS JOIN guild_quest_templates t
            WHERE t.type = 'milestone' AND t.is_active = true
            ON CONFLICT DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_guild_quest_player_buffs_player", table_name="guild_quest_player_buffs")
    op.drop_table("guild_quest_player_buffs")
    op.drop_table("guild_weekly_quest_ballots")
    op.drop_table("guild_quest_contributions")
    op.drop_index("ix_guild_quests_guild_status", table_name="guild_quests")
    op.drop_table("guild_quests")
    op.drop_table("guild_quest_tiers")
    op.drop_index("ix_guild_quest_templates_type", table_name="guild_quest_templates")
    op.drop_index("ix_guild_quest_templates_metric", table_name="guild_quest_templates")
    op.drop_table("guild_quest_templates")
