"""Capture group-chat audio files and serve them as cached tavern BGM.

Only real audio files (``message.audio``) are saved — voice messages (``message.voice``)
are intentionally ignored. Files are downloaded once, written under ``static/`` and
deduplicated by Telegram ``file_unique_id`` so we never re-download the same track.
"""
from __future__ import annotations

import logging
import re
from io import BytesIO
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import ChatAudioTrack
from waifu_bot.db.session import get_session
from waifu_bot.paths import repository_root
from waifu_bot.services.player_chats import resolve_player_group_chats

logger = logging.getLogger(__name__)

# Telegram Bot API getFile is limited to ~20 MB downloads.
MAX_AUDIO_BYTES = 20 * 1024 * 1024

_MIME_EXT = {
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/ogg": ".ogg",
    "audio/opus": ".ogg",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/aac": ".aac",
    "audio/flac": ".flac",
    "audio/x-flac": ".flac",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/webm": ".weba",
}

_ALLOWED_EXT = {".mp3", ".ogg", ".m4a", ".aac", ".flac", ".wav", ".weba"}


def _static_root() -> Path:
    return repository_root() / "static"


def _safe_component(value: str, fallback: str = "x") -> str:
    out = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "").strip()).strip("_")
    return out[:80] or fallback


def _ext_for_audio(file_name: str | None, mime_type: str | None) -> str:
    if file_name:
        suffix = Path(str(file_name)).suffix.lower()
        if suffix in _ALLOWED_EXT:
            return suffix
    return _MIME_EXT.get((mime_type or "").lower(), ".mp3")


async def save_chat_audio_from_message(bot, message) -> None:
    """Best-effort: persist an ``message.audio`` track for the message's group chat.

    Safe to call on every group message; it returns early when there is no audio,
    the chat is not a group, or the track is already cached.
    """
    audio = getattr(message, "audio", None)
    if audio is None:
        return
    chat = getattr(message, "chat", None)
    chat_id = int(getattr(chat, "id", 0) or 0)
    if chat_id >= 0:  # group/supergroup chat ids are negative
        return

    file_unique_id = str(getattr(audio, "file_unique_id", "") or "").strip()
    file_id = str(getattr(audio, "file_id", "") or "").strip()
    if not file_unique_id or not file_id:
        return

    file_size = getattr(audio, "file_size", None)
    if file_size and int(file_size) > MAX_AUDIO_BYTES:
        logger.info("[TAVERN AUDIO] skip oversized audio file_size=%s chat=%s", file_size, chat_id)
        return

    try:
        async for session in get_session():
            existing = await session.scalar(
                select(ChatAudioTrack.id).where(ChatAudioTrack.file_unique_id == file_unique_id)
            )
            if existing:
                return

            ext = _ext_for_audio(getattr(audio, "file_name", None), getattr(audio, "mime_type", None))
            rel_dir = f"game/tavern_tracks/{_safe_component(str(chat_id), 'chat')}"
            rel_path = f"{rel_dir}/{_safe_component(file_unique_id, 'track')}{ext}"
            dest = _static_root() / rel_path

            # Download from Telegram (aiogram 3).
            tg_file = await bot.get_file(file_id)
            buf = BytesIO()
            await bot.download_file(tg_file.file_path, buf)
            raw = buf.getvalue()
            if not raw:
                logger.warning("[TAVERN AUDIO] empty download chat=%s uid=%s", chat_id, file_unique_id)
                return
            if len(raw) > MAX_AUDIO_BYTES:
                logger.info("[TAVERN AUDIO] skip oversized download bytes=%s", len(raw))
                return

            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)

            track = ChatAudioTrack(
                chat_id=chat_id,
                file_unique_id=file_unique_id,
                file_id=file_id,
                relative_path=rel_path,
                title=(getattr(audio, "title", None) or None),
                performer=(getattr(audio, "performer", None) or None),
                duration=(int(audio.duration) if getattr(audio, "duration", None) else None),
                mime_type=(getattr(audio, "mime_type", None) or None),
                file_size=len(raw),
                uploader_player_id=int(message.from_user.id) if getattr(message, "from_user", None) else None,
            )
            session.add(track)
            await session.commit()
            logger.info(
                "[TAVERN AUDIO] cached track chat=%s uid=%s bytes=%s path=%s",
                chat_id, file_unique_id, len(raw), rel_path,
            )
            return
    except Exception:
        logger.exception("[TAVERN AUDIO] failed to cache audio chat=%s uid=%s", chat_id, file_unique_id)


async def list_tracks_for_player(session: AsyncSession, player_id: int, limit: int = 50) -> list[dict]:
    """Tracks from every group chat the player belongs to, newest first."""
    chat_ids = await resolve_player_group_chats(session, player_id)
    if not chat_ids:
        return []
    stmt = (
        select(ChatAudioTrack)
        .where(ChatAudioTrack.chat_id.in_(chat_ids))
        .order_by(ChatAudioTrack.created_at.desc(), ChatAudioTrack.id.desc())
        .limit(int(limit))
    )
    rows = list((await session.execute(stmt)).scalars().all())
    out: list[dict] = []
    for t in rows:
        out.append(
            {
                "id": int(t.id),
                "url": f"/static/{t.relative_path}",
                "title": t.title,
                "performer": t.performer,
                "duration": t.duration,
            }
        )
    return out
