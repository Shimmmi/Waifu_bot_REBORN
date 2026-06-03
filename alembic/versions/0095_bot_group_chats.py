"""bot_group_chats registry for Armory admin monitoring.

Revision ID: 0095_bot_group_chats
Revises: 0094_dismantle_dust_rebalance
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0095_bot_group_chats"
down_revision: Union[str, None] = "0094_dismantle_dust_rebalance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bot_group_chats",
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_type", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=True),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("invite_link", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "discovered_via",
            sa.String(length=32),
            nullable=False,
            server_default="my_chat_member",
        ),
        sa.PrimaryKeyConstraint("chat_id"),
    )
    op.create_index("ix_bot_group_chats_status", "bot_group_chats", ["status"])
    op.create_index("ix_bot_group_chats_last_activity_at", "bot_group_chats", ["last_activity_at"])


def downgrade() -> None:
    op.drop_index("ix_bot_group_chats_last_activity_at", table_name="bot_group_chats")
    op.drop_index("ix_bot_group_chats_status", table_name="bot_group_chats")
    op.drop_table("bot_group_chats")
