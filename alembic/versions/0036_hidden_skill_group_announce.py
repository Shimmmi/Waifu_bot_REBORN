"""Hidden skills: announce_in_group flag for group chat unlock messages.

Revision ID: 0036_hidden_skill_group_announce
Revises: 0035_hidden_skills
Create Date: 2026-03-21
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0036_hidden_skill_group_announce"
down_revision: Union[str, None] = "0035_hidden_skills"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "hidden_skill_definitions",
        sa.Column("announce_in_group", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.alter_column("hidden_skill_definitions", "announce_in_group", server_default=None)

    # По умолчанию анонс для заметных навыков; остальные можно включить в БД.
    op.execute(
        sa.text(
            """
            UPDATE hidden_skill_definitions SET announce_in_group = true
            WHERE id IN (
                'chatterbox', 'early_bird', 'night_owl', 'marathon', 'consistent',
                'speedster', 'stoic', 'sticker_master', 'photographer', 'legend',
                'executioner', 'boss_slayer', 'elite_hunter', 'dungeon_diver',
                'team_player', 'expedition_veteran', 'loyal_commander', 'perfectionist',
                'enchanter_soul', 'gambler', 'merchant_friend'
            )
            """
        )
    )


def downgrade() -> None:
    op.drop_column("hidden_skill_definitions", "announce_in_group")
