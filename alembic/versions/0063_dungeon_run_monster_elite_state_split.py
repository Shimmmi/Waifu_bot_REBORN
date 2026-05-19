"""Elite behavior state JSON, media block counter, split clone flag on run monsters.

Revision ID: 0063_dungeon_run_monster_elite_state_split
Revises: 0062_item_art_key_widen
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0063_dungeon_run_monster_elite_state_split"
down_revision: Union[str, None] = "0062_item_art_key_widen"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dungeon_run_monsters",
        sa.Column("elite_state", sa.JSON(), nullable=True),
    )
    op.add_column(
        "dungeon_run_monsters",
        sa.Column(
            "media_messages_on_monster",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "dungeon_run_monsters",
        sa.Column(
            "is_split_clone",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("dungeon_run_monsters", "is_split_clone")
    op.drop_column("dungeon_run_monsters", "media_messages_on_monster")
    op.drop_column("dungeon_run_monsters", "elite_state")
