"""Cached group-chat audio tracks for tavern BGM.

Revision ID: 0081_chat_audio_tracks
Revises: 0080_hidden_skill_marathon_reset
Create Date: 2026-05-29
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0081_chat_audio_tracks"
down_revision: Union[str, None] = "0080_hidden_skill_marathon_reset"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_audio_tracks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("file_unique_id", sa.String(length=128), nullable=False),
        sa.Column("file_id", sa.String(length=256), nullable=False),
        sa.Column("relative_path", sa.String(length=512), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=True),
        sa.Column("performer", sa.String(length=256), nullable=True),
        sa.Column("duration", sa.Integer(), nullable=True),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("uploader_player_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_unique_id", name="uq_chat_audio_tracks_file_unique_id"),
    )
    op.create_index("ix_chat_audio_tracks_chat_id", "chat_audio_tracks", ["chat_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_audio_tracks_chat_id", table_name="chat_audio_tracks")
    op.drop_table("chat_audio_tracks")
