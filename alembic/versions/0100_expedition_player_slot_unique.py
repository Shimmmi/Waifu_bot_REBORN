"""Partial unique index: one expedition per player per daily slot.

Revision ID: 0100_expedition_player_slot_unique
Revises: 0099_guild_founder_player_id
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0100_expedition_player_slot_unique"
down_revision: Union[str, None] = "0099_guild_founder_player_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Keep earliest run per (player_id, expedition_slot_id); cancel/unlock dupes.
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY player_id, expedition_slot_id
                       ORDER BY id
                   ) AS rn
            FROM active_expeditions
            WHERE expedition_slot_id IS NOT NULL
        ),
        dupes AS (
            SELECT id FROM ranked WHERE rn > 1
        )
        UPDATE active_expeditions ae
        SET expedition_slot_id = NULL,
            cancelled = TRUE,
            claimed = TRUE,
            finished_at = COALESCE(ae.finished_at, NOW())
        FROM dupes d
        WHERE ae.id = d.id
          AND ae.claimed = FALSE
          AND ae.cancelled = FALSE
        """
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY player_id, expedition_slot_id
                       ORDER BY id
                   ) AS rn
            FROM active_expeditions
            WHERE expedition_slot_id IS NOT NULL
        ),
        dupes AS (
            SELECT id FROM ranked WHERE rn > 1
        )
        UPDATE active_expeditions ae
        SET expedition_slot_id = NULL
        FROM dupes d
        WHERE ae.id = d.id
          AND (ae.claimed = TRUE OR ae.cancelled = TRUE)
        """
    )
    op.execute(
        """
        UPDATE hired_waifus hw
        SET expedition_id = NULL
        FROM active_expeditions ae
        WHERE hw.expedition_id = ae.id
          AND ae.expedition_slot_id IS NULL
          AND ae.cancelled = TRUE
          AND ae.claimed = TRUE
          AND ae.finished_at IS NOT NULL
          AND hw.expedition_id IS NOT NULL
        """
    )
    op.create_index(
        "uq_active_expedition_player_slot",
        "active_expeditions",
        ["player_id", "expedition_slot_id"],
        unique=True,
        postgresql_where=sa.text("expedition_slot_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_active_expedition_player_slot",
        table_name="active_expeditions",
        postgresql_where=sa.text("expedition_slot_id IS NOT NULL"),
    )
