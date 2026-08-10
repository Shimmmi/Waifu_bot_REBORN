"""Privacy: purge stored user message bodies; add message_length.

Revision ID: 0126_privacy_purge_message_text
Revises: 0125_gd_stop_balance_narrative
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0126_privacy_purge_message_text"
down_revision: Union[str, None] = "0125_gd_stop_balance_narrative"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "battle_logs",
        sa.Column("message_length", sa.Integer(), nullable=True),
    )
    # Backfill length from legacy text where present, then purge bodies.
    op.execute(
        """
        UPDATE battle_logs
        SET message_length = CHAR_LENGTH(message_text)
        WHERE message_text IS NOT NULL
          AND message_length IS NULL
        """
    )
    op.execute("UPDATE battle_logs SET message_text = NULL WHERE message_text IS NOT NULL")

    # Guild raid chat event previews (if table exists from 0101).
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if insp.has_table("guild_raid_chat_events"):
        cols = {c["name"] for c in insp.get_columns("guild_raid_chat_events")}
        if "text_preview" in cols:
            op.execute(
                "UPDATE guild_raid_chat_events SET text_preview = NULL "
                "WHERE text_preview IS NOT NULL"
            )


def downgrade() -> None:
    op.drop_column("battle_logs", "message_length")
