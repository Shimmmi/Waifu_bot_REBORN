"""Group-chat audio tracks cached for tavern background music."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, func
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
