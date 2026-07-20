"""Drop battle_logs.message_text (privacy: length-only retention).

Revision ID: 0127_drop_battle_logs_message_text
Revises: 0126_privacy_purge_message_text
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0127_drop_battle_logs_message_text"
down_revision: Union[str, None] = "0126_privacy_purge_message_text"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE battle_logs SET message_text = NULL WHERE message_text IS NOT NULL")
    op.drop_column("battle_logs", "message_text")


def downgrade() -> None:
    op.add_column(
        "battle_logs",
        sa.Column("message_text", sa.Text(), nullable=True),
    )
