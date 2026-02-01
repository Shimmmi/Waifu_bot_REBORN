"""dungeon procedural generation tables (templates, pools, runs)

Revision ID: 0005_dungeon_runs_and_pools
Revises: 0004_dungeon_meta_rewards
Create Date: 2026-01-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_dungeon_runs_and_pools"
down_revision: Union[str, None] = "0004_dungeon_meta_rewards"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "monster_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("emoji", sa.String(length=16), nullable=True),
        sa.Column("family", sa.String(length=32), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("act_min", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("act_max", sa.Integer(), nullable=False, server_default=sa.text("5")),
        sa.Column("level_min", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("level_max", sa.Integer(), nullable=False, server_default=sa.text("50")),
        sa.Column("weight", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("base_difficulty", sa.Integer(), nullable=False, server_default=sa.text("10")),
        sa.Column("hp_base", sa.Integer(), nullable=False, server_default=sa.text("40")),
        sa.Column("hp_per_level", sa.Integer(), nullable=False, server_default=sa.text("10")),
        sa.Column("dmg_base", sa.Integer(), nullable=False, server_default=sa.text("5")),
        sa.Column("dmg_per_level", sa.Integer(), nullable=False, server_default=sa.text("2")),
        sa.Column("exp_base", sa.Integer(), nullable=False, server_default=sa.text("10")),
        sa.Column("exp_per_level", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("gold_base", sa.Integer(), nullable=False, server_default=sa.text("5")),
        sa.Column("gold_per_level", sa.Integer(), nullable=False, server_default=sa.text("2")),
        sa.Column("boss_allowed", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("boss_hp_mult", sa.Float(), nullable=False, server_default=sa.text("2.5")),
        sa.Column("boss_dmg_mult", sa.Float(), nullable=False, server_default=sa.text("1.8")),
        sa.Column("boss_reward_mult", sa.Float(), nullable=False, server_default=sa.text("2.0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "dungeon_pools",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("location_type", sa.String(length=32), nullable=False),
        sa.Column("act", sa.Integer(), nullable=False),
        sa.Column("dungeon_type", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("location_type", "act", "dungeon_type", name="uq_dungeon_pool_key"),
    )

    op.create_table(
        "dungeon_pool_entries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("pool_id", sa.Integer(), sa.ForeignKey("dungeon_pools.id", ondelete="CASCADE")),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("monster_templates.id", ondelete="CASCADE")),
        sa.Column("weight", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("min_difficulty", sa.Integer(), nullable=True),
        sa.Column("max_difficulty", sa.Integer(), nullable=True),
        sa.Column("boss_only", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("exclude_boss", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    op.create_table(
        "dungeon_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id")),
        sa.Column("dungeon_id", sa.Integer(), sa.ForeignKey("dungeons.id")),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'active'")),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("current_position", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("total_monsters", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("total_damage_dealt", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_gold_gained", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_exp_gained", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("energy_spent", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("waifu_hp_lost", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_dungeon_runs_player_status", "dungeon_runs", ["player_id", "status"])

    op.create_table(
        "dungeon_run_monsters",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("dungeon_runs.id", ondelete="CASCADE")),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("monster_templates.id"), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("emoji", sa.String(length=16), nullable=True),
        sa.Column("family", sa.String(length=32), nullable=True),
        sa.Column("is_boss", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("difficulty", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("max_hp", sa.Integer(), nullable=False),
        sa.Column("current_hp", sa.Integer(), nullable=False),
        sa.Column("damage", sa.Integer(), nullable=False),
        sa.Column("exp_reward", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("gold_reward", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.UniqueConstraint("run_id", "position", name="uq_dungeon_run_monsters_run_pos"),
    )
    op.create_index("ix_dungeon_run_monsters_run_pos", "dungeon_run_monsters", ["run_id", "position"])

    op.create_table(
        "drop_rules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("act", sa.Integer(), nullable=False),
        sa.Column("boss_only", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("chance", sa.Float(), nullable=False, server_default=sa.text("0.05")),
        sa.Column("rarity_weights", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("drop_rules")
    op.drop_index("ix_dungeon_run_monsters_run_pos", table_name="dungeon_run_monsters")
    op.drop_table("dungeon_run_monsters")
    op.drop_index("ix_dungeon_runs_player_status", table_name="dungeon_runs")
    op.drop_table("dungeon_runs")
    op.drop_table("dungeon_pool_entries")
    op.drop_table("dungeon_pools")
    op.drop_table("monster_templates")

