"""Group-chat audio tracks cached for tavern background music."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from waifu_bot.db.base import Base


class ChatAudioTrack(Base):
    """An audio file (NOT a voice message) dropped into a group chat and cached on disk.

    The file is stored under ``static/`` once (deduped by Telegram ``file_unique_id``) and
    replayed as tavern BGM for players who belong to that chat.
    """

    __tablename__ = "chat_audio_tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # Stable across re-uploads of the same file → primary dedupe key.
    file_unique_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    # Telegram file_id (can change); kept for reference / re-download.
    file_id: Mapped[str] = mapped_column(String(256), nullable=False)
    # Path relative to the static mount, e.g. "game/tavern_tracks/<chat>/<uid>.mp3".
    relative_path: Mapped[str] = mapped_column(String(512), nullable=False)
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    performer: Mapped[str | None] = mapped_column(String(256), nullable=True)
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uploader_player_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ChatAudioCapturePending(Base):
    """In-flight or failed tavern BGM capture — stores Telegram file_id for admin retry."""

    __tablename__ = "chat_audio_capture_pending"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    file_unique_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    file_id: Mapped[str] = mapped_column(String(256), nullable=False)
    file_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    performer: Mapped[str | None] = mapped_column(String(256), nullable=True)
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uploader_player_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PlayerBgmPlaylist(Base):
    """A named BGM playlist owned by a player for one group chat."""

    __tablename__ = "player_bgm_playlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    shuffle: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    repeat: Mapped[str] = mapped_column(String(8), nullable=False, default="all")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PlayerBgmPlaylistTrack(Base):
    """Ordered track membership in a player BGM playlist."""

    __tablename__ = "player_bgm_playlist_tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    playlist_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("player_bgm_playlists.id", ondelete="CASCADE"), nullable=False
    )
    track_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("chat_audio_tracks.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class PlayerBgmPrefs(Base):
    """Per-player tavern BGM preferences (active playlist for playback)."""

    __tablename__ = "player_bgm_prefs"

    player_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    active_playlist_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("player_bgm_playlists.id", ondelete="SET NULL"), nullable=True
    )
