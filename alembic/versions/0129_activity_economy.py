"""Activity economy: inventory/run tagging, input state, catalog, config.

Revision ID: 0129_activity_economy
Revises: 0128_main_waifu_paperdoll_cosmetics
Create Date: 2026-07-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0129_activity_economy"
down_revision: Union[str, None] = "0128_main_waifu_paperdoll_cosmetics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_CONFIG_SEED = [
    ("activity.chunk_mode", "fill_cap", "fill_cap|exact_min — how activity units are spent per hit"),
    ("activity.max_hits_per_claim", "20", "Max TEXT-equivalent hits applied in one /activity/input/claim"),
    ("activity.max_units_per_claim", "2000", "Max units accepted from client per claim (before buffer)"),
    ("activity.max_steps_per_day", "20000", "UTC day cap for mobile_steps accepted units"),
    ("activity.max_clicks_per_day", "50000", "UTC day cap for steam_clicks accepted units"),
    ("activity.max_step_rate_per_sec", "4", "Anti-cheat ceiling: steps per elapsed second"),
    ("activity.length_cap", "200", "Max units spent on a single activity hit (TEXT length cap)"),
]


def upgrade() -> None:
    op.add_column(
        "inventory_items",
        sa.Column("economy", sa.String(length=16), server_default="telegram", nullable=False),
    )
    op.create_index("ix_inventory_items_player_economy", "inventory_items", ["player_id", "economy"])

    op.add_column(
        "dungeon_runs",
        sa.Column("economy", sa.String(length=16), server_default="telegram", nullable=False),
    )
    op.create_index("ix_dungeon_runs_player_economy_status", "dungeon_runs", ["player_id", "economy", "status"])

    op.create_table(
        "activity_input_state",
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("buffer_units", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_counter", sa.BigInteger(), nullable=True),
        sa.Column("last_claim_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("units_accepted_today", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hits_applied_today", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("day_utc", sa.String(length=10), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "activity_item_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(length=64), nullable=False, unique=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slot_type", sa.String(length=32), nullable=False),
        sa.Column("weapon_type", sa.String(length=32), nullable=True),
        sa.Column("attack_type", sa.String(length=16), nullable=True),
        sa.Column("attack_speed", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("damage_min", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("damage_max", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("base_stat", sa.String(length=32), nullable=True),
        sa.Column("base_stat_value", sa.Integer(), nullable=True),
        sa.Column("required_level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_starter", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.execute(
        """
        INSERT INTO activity_item_templates
            (slug, name, slot_type, weapon_type, attack_type, attack_speed,
             damage_min, damage_max, base_stat, base_stat_value, required_level, is_starter)
        VALUES
            ('activity_starter_dagger', 'Кинжал странника', 'weapon_1h', 'dagger', 'melee',
             3, 8, 14, 'agility', 2, 1, true)
        ON CONFLICT (slug) DO NOTHING
        """
    )

    conn = op.get_bind()
    for key, value, description in NEW_CONFIG_SEED:
        conn.execute(
            sa.text(
                "INSERT INTO game_config (key, value, description) "
                "VALUES (:k, :v, :d) ON CONFLICT (key) DO NOTHING"
            ),
            {"k": key, "v": value, "d": description},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for key, _, _ in NEW_CONFIG_SEED:
        conn.execute(sa.text("DELETE FROM game_config WHERE key = :k"), {"k": key})
    op.drop_table("activity_item_templates")
    op.drop_table("activity_input_state")
    op.drop_index("ix_dungeon_runs_player_economy_status", table_name="dungeon_runs")
    op.drop_column("dungeon_runs", "economy")
    op.drop_index("ix_inventory_items_player_economy", table_name="inventory_items")
    op.drop_column("inventory_items", "economy")
