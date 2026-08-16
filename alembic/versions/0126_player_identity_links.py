"""Steam-client Этап 1: player_identity_links table + synthetic id sequence.

Adds the multi-platform identity table (Telegram/Steam/future Apple/Google)
and a sequence used to allocate negative synthetic Player.id values for
players who first appear via a non-Telegram platform (e.g. launch the Steam
client without ever having used the Telegram bot). Negative ids can never
collide with real Telegram user ids (always positive), so the existing
Telegram auth path (Player.id == telegram user id) is completely unaffected.

Revision ID: 0126_player_identity_links
Revises: 0125_gd_stop_balance_narrative
Create Date: 2026-07-01
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0126_player_identity_links"
down_revision: Union[str, None] = "0125_gd_stop_balance_narrative"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "player_identity_links",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "external_id", name="uq_player_identity_provider_external"),
    )
    op.create_index(
        "ix_player_identity_links_player_id",
        "player_identity_links",
        ["player_id"],
    )

    # Negative ids for Steam-native (non-Telegram) players. START WITH -1, INCREMENT BY -1
    # so newly minted ids are -1, -2, -3, ... and never collide with positive Telegram ids.
    op.execute(
        sa.text(
            "CREATE SEQUENCE IF NOT EXISTS player_synthetic_id_seq "
            "START WITH -1 INCREMENT BY -1 MINVALUE -9223372036854775808 MAXVALUE -1"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP SEQUENCE IF EXISTS player_synthetic_id_seq"))
    op.drop_index("ix_player_identity_links_player_id", table_name="player_identity_links")
    op.drop_table("player_identity_links")
