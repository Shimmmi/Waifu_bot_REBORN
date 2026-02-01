"""Group Dungeon (GD) tables: sessions, contributions, templates, activity, events.

Revision ID: 0015_gd_tables
Revises: 0014_expeditions_base
Create Date: 2026-01-31

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0015_gd_tables"
down_revision: str | None = "0014_expeditions_base"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "gd_dungeon_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("hp_multiplier", sa.Float(), nullable=False),
        sa.Column("thematic_bonus_description", sa.String(255), nullable=True),
        sa.Column("thematic_bonus_class_ids", sa.JSON(), nullable=True),
        sa.Column("unique_event_key", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "gd_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("dungeon_template_id", sa.Integer(), sa.ForeignKey("gd_dungeon_templates.id"), nullable=False),
        sa.Column("current_stage", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("current_monster_hp", sa.Integer(), nullable=False),
        sa.Column("stage_base_hp", sa.Integer(), nullable=False),
        sa.Column("stage_monsters", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_save_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active_event_id", sa.Integer(), nullable=True),
        sa.Column("event_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("event_50_done", sa.JSON(), nullable=True),
        sa.Column("event_10_done", sa.JSON(), nullable=True),
        sa.Column("adaptive_regressions_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'active'")),
    )
    op.create_index("ix_gd_sessions_chat_id", "gd_sessions", ["chat_id"], unique=False)
    op.create_index("ix_gd_sessions_status", "gd_sessions", ["status"], unique=False)

    op.create_table(
        "gd_player_contributions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("gd_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("total_damage", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("events_completed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("joined_at_stage", sa.Integer(), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("damage_multiplier", sa.Float(), nullable=False, server_default=sa.text("1.0")),
    )
    op.create_index("ix_gd_player_contributions_session", "gd_player_contributions", ["session_id"], unique=False)
    op.create_index("ix_gd_player_contributions_user", "gd_player_contributions", ["user_id"], unique=False)

    op.create_table(
        "player_chat_first_seen",
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id"), primary_key=True),
        sa.Column("chat_id", sa.BigInteger(), primary_key=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_player_chat_first_seen_chat", "player_chat_first_seen", ["chat_id"], unique=False)

    op.create_table(
        "player_game_actions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("action_type", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_player_game_actions_player_chat", "player_game_actions", ["player_id", "chat_id"], unique=False)
    op.create_index("ix_player_game_actions_created", "player_game_actions", ["created_at"], unique=False)

    op.create_table(
        "gd_event_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("trigger_type", sa.String(32), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=True),
        sa.Column("content_type", sa.String(32), nullable=True),
        sa.Column("emoji_filter", sa.String(128), nullable=True),
        sa.Column("effect_type", sa.String(32), nullable=True),
        sa.Column("min_players_required", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("duration_seconds", sa.Integer(), nullable=False, server_default=sa.text("45")),
        sa.Column("weight", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("dungeon_event_key", sa.String(64), nullable=True),
        sa.Column("name", sa.String(128), nullable=True),
    )
    op.create_index("ix_gd_event_templates_trigger", "gd_event_templates", ["trigger_type"], unique=False)

    op.create_table(
        "gd_completions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("dungeon_template_id", sa.Integer(), sa.ForeignKey("gd_dungeon_templates.id"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_gd_completions_template", "gd_completions", ["dungeon_template_id"], unique=False)
    op.create_index("ix_gd_completions_finished", "gd_completions", ["finished_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_gd_completions_finished", table_name="gd_completions")
    op.drop_index("ix_gd_completions_template", table_name="gd_completions")
    op.drop_table("gd_completions")
    op.drop_index("ix_gd_event_templates_trigger", table_name="gd_event_templates")
    op.drop_table("gd_event_templates")
    op.drop_index("ix_player_game_actions_created", table_name="player_game_actions")
    op.drop_index("ix_player_game_actions_player_chat", table_name="player_game_actions")
    op.drop_table("player_game_actions")
    op.drop_index("ix_player_chat_first_seen_chat", table_name="player_chat_first_seen")
    op.drop_table("player_chat_first_seen")
    op.drop_index("ix_gd_player_contributions_user", table_name="gd_player_contributions")
    op.drop_index("ix_gd_player_contributions_session", table_name="gd_player_contributions")
    op.drop_table("gd_player_contributions")
    op.drop_index("ix_gd_sessions_status", table_name="gd_sessions")
    op.drop_index("ix_gd_sessions_chat_id", table_name="gd_sessions")
    op.drop_table("gd_sessions")
    op.drop_table("gd_dungeon_templates")
