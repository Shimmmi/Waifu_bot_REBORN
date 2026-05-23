"""Chat activity rewards: wallet, daily/total tracking, passive nodes, guild skill.

Revision ID: 0073_chat_activity_rewards
Revises: 0072_expedition_narrative
Create Date: 2026-05-23
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0073_chat_activity_rewards"
down_revision: Union[str, None] = "0072_expedition_narrative"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "player_chat_reward_wallets",
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("gold", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("exp", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pending_chests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_buffered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_claimed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "player_chat_activity_daily",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("gold_earned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("exp_earned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("messages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chests_granted", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("player_id", "day", name="uq_player_chat_activity_daily_player_day"),
    )
    op.create_index(
        "ix_player_chat_activity_daily_player_day",
        "player_chat_activity_daily",
        ["player_id", "day"],
    )

    op.create_table(
        "player_chat_activity_totals",
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("lifetime_points", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("chests_unlocked_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_chest_at", sa.DateTime(timezone=True), nullable=True),
    )

    cfg_rows = [
        ("chat_reward.min_chars", "3", "Мин. длина текста для награды за чат"),
        ("chat_reward.min_seconds_between_msgs", "8", "Кулдаун между засчитываемыми сообщениями (с)"),
        ("chat_reward.daily_points_cap", "600", "Дневной cap баллов активности в чате (UTC)"),
        ("chat_reward.points_per_msg_cap", "5", "Макс. баллов за одно сообщение"),
        ("chat_reward.chars_per_point", "40", "Символов текста за +1 балл"),
        ("chat_reward.max_text_bonus", "4", "Макс. бонус баллов от длины текста"),
        ("chat_reward.gold_per_point", "2", "Золото за балл активности"),
        ("chat_reward.exp_per_point", "3", "Опыт ОВ за балл активности"),
        ("chat_reward.chest_milestone_step", "1000", "Баллов lifetime до сундука"),
        ("chat_reward.chest_min_item_level_offset", "-2", "Смещение ilvl сундука от уровня ОВ"),
    ]
    for key, val, desc in cfg_rows:
        op.execute(
            sa.text(
                "INSERT INTO game_config (key, value, description) VALUES (:k, :v, :d) "
                "ON CONFLICT (key) DO NOTHING"
            ).bindparams(k=key, v=val, d=desc)
        )

    passive_nodes = [
        (
            "sa_chatter",
            "sage",
            2,
            4,
            "Болтун",
            3,
            10,
            5,
            "chat_gold_pct",
            [0.05, 0.10, 0.18],
            1500,
            "Бонус золота за активность в групповом чате",
        ),
        (
            "sh_lurker",
            "shadow",
            3,
            4,
            "Теневой собеседник",
            3,
            25,
            15,
            "chat_exp_pct",
            [0.08, 0.15, 0.25],
            2500,
            "Бонус опыта за активность в групповом чате",
        ),
    ]
    for row in passive_nodes:
        nid, branch, tier, pos, name, mx, wl, bp, et, ev, cost, desc = row
        op.execute(
            sa.text(
                "INSERT INTO passive_skill_nodes "
                "(id, branch, tier, position, name, max_level, waifu_level_req, branch_points_req, "
                "effect_type, effect_values, cost_gold, description) "
                "VALUES (:id, :branch, :tier, :pos, :name, :mx, :wl, :bp, :et, CAST(:ev AS JSONB), :cost, :desc) "
                "ON CONFLICT (id) DO NOTHING"
            ).bindparams(
                id=nid,
                branch=branch,
                tier=tier,
                pos=pos,
                name=name,
                mx=mx,
                wl=wl,
                bp=bp,
                et=et,
                ev=json.dumps(ev),
                cost=cost,
                desc=desc,
            )
        )

    op.execute(
        sa.text(
            "INSERT INTO guild_skill_definitions "
            "(name, tier, effect_param, effect_per_level, guild_level_req, cost_sp, cost_per_upgrade, sort_order) "
            "SELECT :n, :t, :p, CAST(:j AS JSON), :g, 1, 1, :so "
            "WHERE NOT EXISTS (SELECT 1 FROM guild_skill_definitions WHERE effect_param = :p AND name = :n)"
        ).bindparams(
            n="Светская гильдия",
            t=2,
            p="chat_reward_pct",
            j=json.dumps([0.05, 0.10, 0.15]),
            g=5,
            so=16,
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM passive_skill_nodes WHERE id IN ('sa_chatter', 'sh_lurker')"))
    op.execute(
        sa.text("DELETE FROM guild_skill_definitions WHERE effect_param = 'chat_reward_pct' AND name = 'Светская гильдия'")
    )
    keys = (
        "chat_reward.min_chars",
        "chat_reward.min_seconds_between_msgs",
        "chat_reward.daily_points_cap",
        "chat_reward.points_per_msg_cap",
        "chat_reward.chars_per_point",
        "chat_reward.max_text_bonus",
        "chat_reward.gold_per_point",
        "chat_reward.exp_per_point",
        "chat_reward.chest_milestone_step",
        "chat_reward.chest_min_item_level_offset",
    )
    for k in keys:
        op.execute(sa.text("DELETE FROM game_config WHERE key = :k").bindparams(k=k))

    op.drop_index("ix_player_chat_activity_daily_player_day", table_name="player_chat_activity_daily")
    op.drop_table("player_chat_activity_totals")
    op.drop_table("player_chat_activity_daily")
    op.drop_table("player_chat_reward_wallets")
