"""Guild raid v2: 4-hour slot summaries table.

Revision ID: 0102_guild_raid_slot_summaries
Revises: 0101_guild_raid_v2_chronicle
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0102_guild_raid_slot_summaries"
down_revision: Union[str, None] = "0101_guild_raid_v2_chronicle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "guild_raid_slot_summaries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("raid_id", sa.Integer(), nullable=False),
        sa.Column("game_date", sa.Date(), nullable=False),
        sa.Column("slot_index", sa.Integer(), nullable=False),
        sa.Column("slot_label", sa.String(length=32), nullable=True),
        sa.Column("summary_html", sa.String(), nullable=True),
        sa.Column("slot_beats_json", sa.JSON(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["raid_id"], ["guild_raids.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("raid_id", "game_date", "slot_index", name="uq_guild_raid_slot_summary"),
    )
    op.create_index(
        "ix_guild_raid_slot_summaries_raid_date",
        "guild_raid_slot_summaries",
        ["raid_id", "game_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_guild_raid_slot_summaries_raid_date", table_name="guild_raid_slot_summaries")
    op.drop_table("guild_raid_slot_summaries")
