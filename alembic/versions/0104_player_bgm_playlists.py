"""Player BGM playlists for tavern music player.

Revision ID: 0104_player_bgm_playlists
Revises: 0103_chat_audio_capture_pending
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0104_player_bgm_playlists"
down_revision: Union[str, None] = "0103_chat_audio_capture_pending"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "player_bgm_playlists",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("shuffle", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("repeat", sa.String(length=8), nullable=False, server_default="all"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_player_bgm_playlists_player_id",
        "player_bgm_playlists",
        ["player_id"],
    )

    op.create_table(
        "player_bgm_playlist_tracks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("playlist_id", sa.Integer(), nullable=False),
        sa.Column("track_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["playlist_id"],
            ["player_bgm_playlists.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["track_id"],
            ["chat_audio_tracks.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "playlist_id",
            "track_id",
            name="uq_player_bgm_playlist_tracks_playlist_track",
        ),
    )
    op.create_index(
        "ix_player_bgm_playlist_tracks_playlist_position",
        "player_bgm_playlist_tracks",
        ["playlist_id", "position"],
    )

    op.create_table(
        "player_bgm_prefs",
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("active_playlist_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["active_playlist_id"],
            ["player_bgm_playlists.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("player_id"),
    )


def downgrade() -> None:
    op.drop_table("player_bgm_prefs")
    op.drop_index(
        "ix_player_bgm_playlist_tracks_playlist_position",
        table_name="player_bgm_playlist_tracks",
    )
    op.drop_table("player_bgm_playlist_tracks")
    op.drop_index("ix_player_bgm_playlists_player_id", table_name="player_bgm_playlists")
    op.drop_table("player_bgm_playlists")
