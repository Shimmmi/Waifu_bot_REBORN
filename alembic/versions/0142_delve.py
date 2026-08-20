"""Delve tables, config, copy from Chronicle, drop Chronicle.

Revision ID: 0142_delve
Revises: 0141_chronicle
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0142_delve"
down_revision: Union[str, None] = "0141_chronicle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "delve_states",
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("t_origin", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_grant_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("gold_granted_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("xp_granted_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("grant_day_msk", sa.String(length=16), nullable=True),
        sa.Column("gold_granted_today", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("xp_granted_today", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("spine_seed", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("pb_depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("committed_palette", sa.String(length=16), nullable=True),
        sa.Column("pending_tint", sa.String(length=16), nullable=True),
        sa.Column("journal_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("title_id", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("sprite_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_reform_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("legacy_names_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("migration_from_chronicle", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("legacy_seen", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("former_gladiator", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("player_id"),
    )
    op.create_index("ix_delve_states_pb_depth", "delve_states", ["pb_depth"])
    op.create_table(
        "delve_companions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("slot", sa.SmallInteger(), nullable=False),
        sa.Column("name", sa.String(length=48), nullable=False),
        sa.Column("stance", sa.String(length=16), nullable=False),
        sa.Column("temper", sa.String(length=16), nullable=False),
        sa.Column("cloak_color", sa.String(length=16), nullable=True),
        sa.Column("image_path", sa.String(length=255), nullable=True),
        sa.Column("portrait_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("player_id", "slot", name="uq_delve_companions_player_slot"),
        sa.CheckConstraint("slot >= 1 AND slot <= 3", name="ck_delve_companion_slot"),
    )
    op.create_index("ix_delve_companions_player_id", "delve_companions", ["player_id"])

    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "chronicle_states" in inspector.get_table_names():
        conn.execute(
            sa.text(
                """
                INSERT INTO delve_states (
                    player_id, t_origin, last_grant_ts, gold_granted_total, xp_granted_total,
                    spine_seed, pb_depth, sprite_count, last_reform_at, legacy_names_json,
                    migration_from_chronicle, legacy_seen, former_gladiator, created_at, updated_at
                )
                SELECT
                    player_id,
                    CASE WHEN started_at IS NOT NULL THEN NOW() ELSE NULL END,
                    CASE WHEN started_at IS NOT NULL THEN NOW() ELSE NULL END,
                    0, 0,
                    COALESCE(sim_seed, 0),
                    0,
                    COALESCE(sprite_count, 0),
                    last_reform_at,
                    legacy_names_json,
                    CASE WHEN started_at IS NOT NULL THEN true ELSE false END,
                    false,
                    COALESCE(former_gladiator, false),
                    created_at,
                    NOW()
                FROM chronicle_states
                ON CONFLICT (player_id) DO NOTHING
                """
            )
        )
    if "chronicle_companions" in inspector.get_table_names():
        conn.execute(
            sa.text(
                """
                INSERT INTO delve_companions (
                    player_id, slot, name, stance, temper, cloak_color, image_path, portrait_attempts, created_at
                )
                SELECT
                    player_id,
                    slot,
                    name,
                    CASE role
                        WHEN 'blade' THEN 'scout'
                        WHEN 'keeper' THEN 'shield'
                        ELSE 'guide'
                    END,
                    CASE motive
                        WHEN 'oath' THEN 'stay'
                        WHEN 'duty' THEN 'stay'
                        WHEN 'rival' THEN 'temper'
                        WHEN 'testimony' THEN 'temper'
                        WHEN 'absence' THEN 'curiosity'
                        WHEN 'sacrifice' THEN 'curiosity'
                        ELSE 'stay'
                    END,
                    cloak_color,
                    image_path,
                    COALESCE(portrait_attempts, 0),
                    created_at
                FROM chronicle_companions
                ON CONFLICT (player_id, slot) DO NOTHING
                """
            )
        )
        op.drop_table("chronicle_companions")
    if "chronicle_states" in inspector.get_table_names():
        op.drop_table("chronicle_states")

    cfg_rows = [
        ("expedition.v3_enabled", "true", "Delve column; legacy expeditions 410"),
        ("delve.enabled", "true", "Delve column master switch"),
        ("delve.gold_of_chat_cap", "0.25", "Column gold floor as fraction of chat gold cap"),
        ("delve.xp_of_solo_day", "0.15", "Column XP floor as fraction of typical solo-day XP"),
        ("guild_gxp.expedition_success", "0", "Delve must not farm GXP"),
        ("guild_war.ws_expedition_success", "0", "Delve must not farm war score"),
    ]
    for key, value, desc in cfg_rows:
        conn.execute(
            sa.text(
                "INSERT INTO game_config (key, value, description) VALUES (:k, :v, :d) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, description = EXCLUDED.description"
            ),
            {"k": key, "v": value, "d": desc},
        )
    conn.execute(sa.text("DELETE FROM game_config WHERE key = 'chronicle.stipend_of_chat_cap'"))


def downgrade() -> None:
    op.drop_index("ix_delve_companions_player_id", table_name="delve_companions")
    op.drop_table("delve_companions")
    op.drop_index("ix_delve_states_pb_depth", table_name="delve_states")
    op.drop_table("delve_states")
