"""Pending tavern BGM captures for admin retry without re-send.

Revision ID: 0103_chat_audio_capture_pending
Revises: 0102_guild_raid_slot_summaries
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0103_chat_audio_capture_pending"
down_revision: Union[str, None] = "0102_guild_raid_slot_summaries"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_audio_capture_pending",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("file_unique_id", sa.String(length=128), nullable=False),
        sa.Column("file_id", sa.String(length=256), nullable=False),
        sa.Column("file_name", sa.String(length=256), nullable=True),
        sa.Column("title", sa.String(length=256), nullable=True),
        sa.Column("performer", sa.String(length=256), nullable=True),
        sa.Column("duration", sa.Integer(), nullable=True),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("uploader_player_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("last_error", sa.String(length=512), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_unique_id", name="uq_chat_audio_capture_pending_file_unique_id"),
    )
    op.create_index(
        "ix_chat_audio_capture_pending_chat_id",
        "chat_audio_capture_pending",
        ["chat_id"],
    )
    op.create_index(
        "ix_chat_audio_capture_pending_status",
        "chat_audio_capture_pending",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_audio_capture_pending_status", table_name="chat_audio_capture_pending")
    op.drop_index("ix_chat_audio_capture_pending_chat_id", table_name="chat_audio_capture_pending")
    op.drop_table("chat_audio_capture_pending")
