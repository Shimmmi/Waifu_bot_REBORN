"""GD daily cycle: game_date, ends_at, day_stats_json.

Revision ID: 0132_gd_daily_cycle
Revises: 0131_merc_gear_bag
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0132_gd_daily_cycle"
down_revision: Union[str, None] = "0131_merc_gear_bag"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("gd_cycles", sa.Column("game_date", sa.Date(), nullable=True))
    op.add_column(
        "gd_cycles",
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_gd_cycles_game_date", "gd_cycles", ["game_date"])
    op.create_index(
        "ix_gd_cycles_chat_game_date",
        "gd_cycles",
        ["chat_id", "game_date"],
        unique=False,
    )
    op.add_column(
        "gd_registrations",
        sa.Column("day_stats_json", sa.JSON(), nullable=True),
    )
    # Seed daily schedule config keys (idempotent upsert via INSERT … ON CONFLICT for PG).
    op.execute(
        """
        INSERT INTO game_config (key, value)
        VALUES
            ('gd_daily_start_hour_msk', '4'),
            ('gd_daily_start_minute_msk', '30'),
            ('gd_daily_end_hour_msk', '4'),
            ('gd_daily_end_minute_msk', '0'),
            ('gd_daily_pie_enabled', '1'),
            ('gd_daily_ai_start', '1'),
            ('gd_daily_ai_finale', '1'),
            ('gd_cooldown_after_finish_hours', '0')
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_column("gd_registrations", "day_stats_json")
    op.drop_index("ix_gd_cycles_chat_game_date", table_name="gd_cycles")
    op.drop_index("ix_gd_cycles_game_date", table_name="gd_cycles")
    op.drop_column("gd_cycles", "ends_at")
    op.drop_column("gd_cycles", "game_date")
