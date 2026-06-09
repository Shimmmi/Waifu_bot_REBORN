"""Capture group-chat audio files and serve them as cached tavern BGM.

``message.audio`` and audio ``message.document`` attachments are saved — voice
messages (``message.voice``) are intentionally ignored. Files are downloaded once,
written under ``static/`` and deduplicated by Telegram ``file_unique_id``.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from aiogram.exceptions import TelegramNetworkError
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.core.config import settings
from waifu_bot.db.models import (
    BotGroupChat,
    ChatAudioCapturePending,
    ChatAudioTrack,
    PlayerBgmPlaylist,
    PlayerBgmPlaylistTrack,
    PlayerBgmPrefs,
)
from waifu_bot.db.session import get_session
from waifu_bot.paths import repository_root
from waifu_bot.services.bot_group_chats import ACTIVE_STATUSES
from waifu_bot.services.player_chats import resolve_player_group_chats

logger = logging.getLogger(__name__)

# Telegram Bot API getFile is limited to ~20 MB downloads.
MAX_AUDIO_BYTES = 20 * 1024 * 1024
_DOWNLOAD_RETRY_ATTEMPTS = 2
_DOWNLOAD_RETRY_DELAY_SEC = 2.0

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

_TAVERN_AUDIO_EVENTS: deque["TavernAudioEvent"] = deque(maxlen=200)


@dataclass
class TavernAudioEvent:
    ts: str
    event: str
    chat_id: int | None
    player_id: int | None
    detail: str


def log_tavern_audio_event(
    event: str,
    *,
    chat_id: int | None = None,
    player_id: int | None = None,
    detail: str = "",
    level: int = logging.INFO,
) -> None:
    entry = TavernAudioEvent(
        ts=datetime.now(tz=timezone.utc).isoformat(),
        event=str(event),
        chat_id=int(chat_id) if chat_id is not None else None,
        player_id=int(player_id) if player_id is not None else None,
        detail=str(detail or "")[:512],
    )
    _TAVERN_AUDIO_EVENTS.appendleft(entry)
    logger.log(
        level,
        "[TAVERN AUDIO] event=%s chat=%s player=%s %s",
        entry.event,
        entry.chat_id,
        entry.player_id,
        entry.detail,
    )


def list_recent_tavern_audio_events(limit: int = 100) -> list[dict[str, Any]]:
    n = max(1, min(int(limit), 200))
    return [asdict(e) for e in list(_TAVERN_AUDIO_EVENTS)[:n]]


def clear_tavern_audio_events_for_tests() -> None:
    _TAVERN_AUDIO_EVENTS.clear()


def describe_tavern_message_media(message) -> str:
    audio = getattr(message, "audio", None)
    if audio is not None:
        return (
            f"kind=audio mime={getattr(audio, 'mime_type', '') or '—'} "
            f"name={getattr(audio, 'file_name', '') or '—'}"
        )
    doc = getattr(message, "document", None)
    if doc is not None:
        return (
            f"kind=document mime={getattr(doc, 'mime_type', '') or '—'} "
            f"name={getattr(doc, 'file_name', '') or '—'}"
        )
    return "kind=unknown"


def log_tavern_audio_enqueue(message, chat_id: int | None, player_id: int | None) -> None:
    log_tavern_audio_event(
        "enqueue",
        chat_id=chat_id,
        player_id=player_id,
        detail=describe_tavern_message_media(message),
    )


def log_tavern_audio_reject_document(message, chat_id: int | None, player_id: int | None) -> None:
    doc = getattr(message, "document", None)
    if doc is None or message_has_tavern_audio(message):
        return
    log_tavern_audio_event(
        "reject_document",
        chat_id=chat_id,
        player_id=player_id,
        detail=describe_tavern_message_media(message),
        level=logging.WARNING,
    )


def log_tavern_audio_task_failed(
    chat_id: int | None,
    player_id: int | None,
    exc: BaseException,
    *,
    meta_bytes: int | None = None,
    received_bytes: int | None = None,
    file_unique_id: str | None = None,
) -> None:
    detail = f"{type(exc).__name__}: {exc}"
    if file_unique_id:
        detail += f" uid={file_unique_id}"
    if meta_bytes is not None:
        detail += f" meta_bytes={meta_bytes}"
    if received_bytes is not None:
        expected_suffix = f"/{meta_bytes}" if meta_bytes is not None else ""
        detail += f" received={received_bytes}{expected_suffix}"
    log_tavern_audio_event(
        "failed",
        chat_id=chat_id,
        player_id=player_id,
        detail=detail,
        level=logging.WARNING,
    )


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


def _is_audio_mime(mime_type: str | None) -> bool:
    mime = (mime_type or "").lower().strip()
    if not mime:
        return False
    if mime.startswith("audio/"):
        return True
    return mime in _MIME_EXT


def _is_audio_file_name(file_name: str | None) -> bool:
    if not file_name:
        return False
    return Path(str(file_name)).suffix.lower() in _ALLOWED_EXT


def _title_from_file_name(file_name: str | None) -> str | None:
    if not file_name:
        return None
    stem = Path(str(file_name)).stem.strip()
    return stem or None


def _audio_attachment_from_message(message) -> dict[str, Any] | None:
    """Unified audio payload from ``message.audio`` or audio ``message.document``."""
    audio = getattr(message, "audio", None)
    if audio is not None:
        file_unique_id = str(getattr(audio, "file_unique_id", "") or "").strip()
        file_id = str(getattr(audio, "file_id", "") or "").strip()
        if not file_unique_id or not file_id:
            return None
        duration = getattr(audio, "duration", None)
        return {
            "file_id": file_id,
            "file_unique_id": file_unique_id,
            "file_name": getattr(audio, "file_name", None),
            "mime_type": getattr(audio, "mime_type", None),
            "file_size": getattr(audio, "file_size", None),
            "title": getattr(audio, "title", None) or None,
            "performer": getattr(audio, "performer", None) or None,
            "duration": int(duration) if duration is not None else None,
        }

    doc = getattr(message, "document", None)
    if doc is None:
        return None
    mime_type = getattr(doc, "mime_type", None)
    file_name = getattr(doc, "file_name", None)
    if not _is_audio_mime(mime_type) and not _is_audio_file_name(file_name):
        return None

    file_unique_id = str(getattr(doc, "file_unique_id", "") or "").strip()
    file_id = str(getattr(doc, "file_id", "") or "").strip()
    if not file_unique_id or not file_id:
        return None

    return {
        "file_id": file_id,
        "file_unique_id": file_unique_id,
        "file_name": file_name,
        "mime_type": mime_type,
        "file_size": getattr(doc, "file_size", None),
        "title": _title_from_file_name(file_name),
        "performer": None,
        "duration": None,
    }


def message_has_tavern_audio(message) -> bool:
    """True when the message carries a capturable audio file (not voice)."""
    return _audio_attachment_from_message(message) is not None


class TelegramFileDownloadError(Exception):
    """Wraps a download failure with partial byte count for diagnostics."""

    def __init__(self, cause: BaseException, *, received_bytes: int = 0) -> None:
        self.received_bytes = received_bytes
        super().__init__(str(cause))
        self.__cause__ = cause


def _telegram_download_safety_cap() -> int:
    return max(60, int(getattr(settings, "telegram_file_download_timeout", 600) or 600))


def _telegram_download_read_timeout() -> float:
    return max(10.0, float(getattr(settings, "telegram_file_download_read_timeout", 60) or 60))


def _httpx_download_timeout() -> httpx.Timeout:
    read_timeout = _telegram_download_read_timeout()
    return httpx.Timeout(connect=30.0, read=read_timeout, write=30.0, pool=30.0)


async def _stream_file_url(url: str) -> bytes:
    """Stream a Telegram file URL with per-chunk read timeout and safety cap."""
    safety_cap = _telegram_download_safety_cap()
    started = time.monotonic()
    chunks: list[bytes] = []

    async with httpx.AsyncClient(timeout=_httpx_download_timeout()) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            async for chunk in resp.aiter_bytes(65536):
                if time.monotonic() - started > safety_cap:
                    received = sum(len(c) for c in chunks)
                    raise TelegramFileDownloadError(
                        asyncio.TimeoutError(f"safety cap {safety_cap}s exceeded"),
                        received_bytes=received,
                    )
                chunks.append(chunk)

    return b"".join(chunks)


async def _download_telegram_file(
    bot,
    file_id: str,
    *,
    chat_id: int | None = None,
    player_id: int | None = None,
    expected_bytes: int | None = None,
) -> bytes:
    """Download file bytes via httpx streaming (slow proxy-safe) with one retry."""
    last_exc: BaseException | None = None
    last_received = 0

    for attempt in range(_DOWNLOAD_RETRY_ATTEMPTS):
        try:
            tg_file = await bot.get_file(file_id, request_timeout=30)
            url = bot.session.api.file_url(bot.token, tg_file.file_path)
            host = urlparse(url).netloc or "?"

            if attempt == 0:
                detail = f"attempt=1 url_host={host}"
                if expected_bytes:
                    detail += f" expected_bytes={expected_bytes}"
                log_tavern_audio_event(
                    "download",
                    chat_id=chat_id,
                    player_id=player_id,
                    detail=detail,
                )
            else:
                log_tavern_audio_event(
                    "download_retry",
                    chat_id=chat_id,
                    player_id=player_id,
                    detail=f"attempt={attempt + 1} received={last_received}",
                )

            return await _stream_file_url(url)
        except (
            asyncio.TimeoutError,
            httpx.TimeoutException,
            httpx.HTTPError,
            TelegramNetworkError,
            TelegramFileDownloadError,
        ) as exc:
            if isinstance(exc, TelegramFileDownloadError):
                last_received = exc.received_bytes
                last_exc = exc.__cause__ or exc
            else:
                last_exc = exc
            if attempt + 1 >= _DOWNLOAD_RETRY_ATTEMPTS:
                if last_received:
                    raise TelegramFileDownloadError(last_exc, received_bytes=last_received) from last_exc
                raise last_exc
            await asyncio.sleep(_DOWNLOAD_RETRY_DELAY_SEC)

    raise last_exc or RuntimeError("telegram file download failed")


def _attachment_from_pending(pending: ChatAudioCapturePending) -> dict[str, Any]:
    return {
        "file_id": pending.file_id,
        "file_unique_id": pending.file_unique_id,
        "file_name": pending.file_name,
        "mime_type": pending.mime_type,
        "file_size": pending.file_size,
        "title": pending.title,
        "performer": pending.performer,
        "duration": pending.duration,
    }


async def _delete_pending_capture(session: AsyncSession, file_unique_id: str) -> None:
    pending = await session.scalar(
        select(ChatAudioCapturePending).where(
            ChatAudioCapturePending.file_unique_id == file_unique_id
        )
    )
    if pending is not None:
        await session.delete(pending)
        await session.commit()


async def _upsert_pending_capture(
    session: AsyncSession,
    attachment: dict[str, Any],
    *,
    chat_id: int,
    player_id: int | None,
    status: str = "downloading",
) -> None:
    uid = str(attachment["file_unique_id"])
    pending = await session.scalar(
        select(ChatAudioCapturePending).where(ChatAudioCapturePending.file_unique_id == uid)
    )
    if pending is None:
        pending = ChatAudioCapturePending(
            chat_id=chat_id,
            file_unique_id=uid,
            file_id=str(attachment["file_id"]),
            file_name=attachment.get("file_name"),
            title=attachment.get("title"),
            performer=attachment.get("performer"),
            duration=attachment.get("duration"),
            mime_type=attachment.get("mime_type"),
            file_size=int(attachment["file_size"]) if attachment.get("file_size") else None,
            uploader_player_id=player_id,
            status=status,
        )
        session.add(pending)
    else:
        pending.chat_id = chat_id
        pending.file_id = str(attachment["file_id"])
        pending.file_name = attachment.get("file_name")
        pending.title = attachment.get("title")
        pending.performer = attachment.get("performer")
        pending.duration = attachment.get("duration")
        pending.mime_type = attachment.get("mime_type")
        pending.file_size = int(attachment["file_size"]) if attachment.get("file_size") else None
        pending.uploader_player_id = player_id
        pending.status = status
        pending.last_error = None
    await session.commit()


async def _mark_pending_failed(
    session: AsyncSession,
    file_unique_id: str,
    error: BaseException,
    *,
    increment_retry: bool = True,
) -> None:
    pending = await session.scalar(
        select(ChatAudioCapturePending).where(
            ChatAudioCapturePending.file_unique_id == file_unique_id
        )
    )
    if pending is None:
        return
    pending.status = "failed"
    pending.last_error = f"{type(error).__name__}: {error}"[:512]
    if increment_retry:
        pending.retry_count = int(pending.retry_count or 0) + 1
    await session.commit()


async def capture_chat_audio_attachment(
    bot,
    attachment: dict[str, Any],
    *,
    chat_id: int,
    player_id: int | None,
    source: str = "message",
) -> dict[str, Any] | None:
    """Download and persist one audio attachment. Returns result dict or None on early exit."""
    file_unique_id = str(attachment["file_unique_id"])
    file_id = str(attachment["file_id"])
    file_size = attachment.get("file_size")
    expected_bytes = int(file_size) if file_size else None

    if file_size and int(file_size) > MAX_AUDIO_BYTES:
        log_tavern_audio_event(
            "skip",
            chat_id=chat_id,
            player_id=player_id,
            detail=f"reason=oversized_meta bytes={file_size}",
        )
        return {"ok": False, "status": "skipped", "reason": "oversized_meta"}

    ext = _ext_for_audio(attachment.get("file_name"), attachment.get("mime_type"))
    rel_dir = f"game/tavern_tracks/{_safe_component(str(chat_id), 'chat')}"
    rel_path = f"{rel_dir}/{_safe_component(file_unique_id, 'track')}{ext}"
    dest = _static_root() / rel_path

    try:
        async for session in get_session():
            existing = await session.scalar(
                select(ChatAudioTrack.id).where(ChatAudioTrack.file_unique_id == file_unique_id)
            )
            if existing:
                await _delete_pending_capture(session, file_unique_id)
                log_tavern_audio_event(
                    "dedupe",
                    chat_id=chat_id,
                    player_id=player_id,
                    detail=f"existing_id={int(existing)} uid={file_unique_id}",
                )
                return {"ok": True, "status": "dedupe", "track_id": int(existing)}

        async for session in get_session():
            await _upsert_pending_capture(
                session,
                attachment,
                chat_id=chat_id,
                player_id=player_id,
                status="downloading",
            )

        raw = await _download_telegram_file(
            bot,
            file_id,
            chat_id=chat_id,
            player_id=player_id,
            expected_bytes=expected_bytes,
        )
        if not raw:
            log_tavern_audio_event(
                "skip",
                chat_id=chat_id,
                player_id=player_id,
                detail=f"reason=empty_download uid={file_unique_id}",
                level=logging.WARNING,
            )
            async for session in get_session():
                await _mark_pending_failed(
                    session,
                    file_unique_id,
                    RuntimeError("empty_download"),
                    increment_retry=False,
                )
            return {"ok": False, "status": "empty_download"}
        if len(raw) > MAX_AUDIO_BYTES:
            log_tavern_audio_event(
                "skip",
                chat_id=chat_id,
                player_id=player_id,
                detail=f"reason=oversized_download bytes={len(raw)}",
            )
            async for session in get_session():
                await _mark_pending_failed(
                    session,
                    file_unique_id,
                    RuntimeError("oversized_download"),
                    increment_retry=False,
                )
            return {"ok": False, "status": "oversized_download"}

        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)

        track_id: int | None = None
        async for session in get_session():
            existing = await session.scalar(
                select(ChatAudioTrack.id).where(ChatAudioTrack.file_unique_id == file_unique_id)
            )
            if existing:
                await _delete_pending_capture(session, file_unique_id)
                log_tavern_audio_event(
                    "dedupe",
                    chat_id=chat_id,
                    player_id=player_id,
                    detail=f"existing_id={int(existing)} uid={file_unique_id}",
                )
                return {"ok": True, "status": "dedupe", "track_id": int(existing)}

            track = ChatAudioTrack(
                chat_id=chat_id,
                file_unique_id=file_unique_id,
                file_id=file_id,
                relative_path=rel_path,
                title=attachment.get("title"),
                performer=attachment.get("performer"),
                duration=attachment.get("duration"),
                mime_type=attachment.get("mime_type"),
                file_size=len(raw),
                uploader_player_id=player_id,
            )
            session.add(track)
            await session.commit()
            await session.refresh(track)
            track_id = int(track.id)
            await _delete_pending_capture(session, file_unique_id)

        log_tavern_audio_event(
            "cached",
            chat_id=chat_id,
            player_id=player_id,
            detail=f"track_id={track_id} bytes={len(raw)} path={rel_path} source={source}",
        )
        return {"ok": True, "status": "cached", "track_id": track_id}
    except Exception as exc:
        meta_bytes = expected_bytes
        received_bytes: int | None = None
        if isinstance(exc, TelegramFileDownloadError):
            received_bytes = exc.received_bytes
            exc = exc.__cause__ or exc
        log_tavern_audio_task_failed(
            chat_id,
            player_id,
            exc,
            meta_bytes=meta_bytes,
            received_bytes=received_bytes,
            file_unique_id=file_unique_id,
        )
        logger.exception("[TAVERN AUDIO] failed to cache audio chat=%s uid=%s", chat_id, file_unique_id)
        async for session in get_session():
            await _mark_pending_failed(session, file_unique_id, exc)
        return {"ok": False, "status": "failed", "error": str(exc)}


async def retry_pending_capture(bot, file_unique_id: str) -> dict[str, Any]:
    """Re-download a failed pending capture using stored Telegram file_id."""
    uid = str(file_unique_id).strip()
    if not uid:
        return {"ok": False, "status": "not_found", "error": "empty file_unique_id"}

    async for session in get_session():
        pending = await session.scalar(
            select(ChatAudioCapturePending).where(ChatAudioCapturePending.file_unique_id == uid)
        )
        if pending is None:
            return {"ok": False, "status": "not_found", "error": f"pending not found uid={uid}"}

        attachment = _attachment_from_pending(pending)
        chat_id = int(pending.chat_id)
        player_id = int(pending.uploader_player_id) if pending.uploader_player_id else None
        attempt = int(pending.retry_count or 0) + 1

    log_tavern_audio_event(
        "retry_manual",
        chat_id=chat_id,
        player_id=player_id,
        detail=f"uid={uid} attempt={attempt}",
    )
    result = await capture_chat_audio_attachment(
        bot,
        attachment,
        chat_id=chat_id,
        player_id=player_id,
        source="retry",
    )
    return result or {"ok": False, "status": "failed", "error": "unknown"}


async def save_chat_audio_from_message(bot, message) -> None:
    """Best-effort: persist group-chat audio from ``message.audio`` or audio document.

    Safe to call on every group message; it returns early when there is no audio,
    the chat is not a group, or the track is already cached.
    """
    chat = getattr(message, "chat", None)
    chat_id = int(getattr(chat, "id", 0) or 0)
    player_id = int(message.from_user.id) if getattr(message, "from_user", None) else None

    attachment = _audio_attachment_from_message(message)
    if attachment is None:
        return
    if chat_id >= 0:  # group/supergroup chat ids are negative
        log_tavern_audio_event(
            "skip",
            chat_id=chat_id,
            player_id=player_id,
            detail="reason=not_group_chat",
        )
        return

    file_unique_id = str(attachment["file_unique_id"])
    file_size = attachment.get("file_size")
    start_detail = f"uid={file_unique_id} title={attachment.get('title') or '—'}"
    if file_size:
        start_detail += f" bytes={file_size}"
    log_tavern_audio_event(
        "start",
        chat_id=chat_id,
        player_id=player_id,
        detail=start_detail,
    )
    if file_size and int(file_size) > MAX_AUDIO_BYTES:
        log_tavern_audio_event(
            "skip",
            chat_id=chat_id,
            player_id=player_id,
            detail=f"reason=oversized_meta bytes={file_size}",
        )
        return

    await capture_chat_audio_attachment(
        bot,
        attachment,
        chat_id=chat_id,
        player_id=player_id,
        source="message",
    )


_BGM_EMPTY_CHATS_HINT = (
    "Отправьте MP3/аудиофайл (файл или аудиозапись, не голосовое) "
    "в групповой чат, где есть вы и бот."
)


def _is_telegram_chat_track(t: ChatAudioTrack) -> bool:
    """Telegram-captured chat audio only; webapp uploads use ``web:`` file_unique_id."""
    return not str(t.file_unique_id or "").startswith("web:")


def _track_dict(t: ChatAudioTrack) -> dict:
    return {
        "id": int(t.id),
        "chat_id": int(t.chat_id),
        "url": f"/static/{t.relative_path}",
        "title": t.title,
        "performer": t.performer,
        "duration": t.duration,
    }


async def _player_active_bot_chat_ids(session: AsyncSession, player_id: int) -> list[int]:
    """Group chats where the player was seen and the bot is still an active member."""
    player_chats = await resolve_player_group_chats(session, player_id)
    if not player_chats:
        return []
    rows = (
        await session.execute(
            select(BotGroupChat.chat_id).where(
                BotGroupChat.chat_id.in_(player_chats),
                BotGroupChat.status.in_(tuple(ACTIVE_STATUSES)),
            )
        )
    ).all()
    return sorted({int(r[0]) for r in rows})


async def list_bgm_chats_for_player(session: AsyncSession, player_id: int) -> dict:
    """Chats available for tavern BGM: player presence ∩ active bot membership."""
    allowed_ids = await _player_active_bot_chat_ids(session, player_id)
    if not allowed_ids:
        return {"chats": [], "hint": _BGM_EMPTY_CHATS_HINT}

    count_rows = (
        await session.execute(
            select(ChatAudioTrack.chat_id, func.count(ChatAudioTrack.id))
            .where(
                ChatAudioTrack.chat_id.in_(allowed_ids),
                ~ChatAudioTrack.file_unique_id.startswith("web:"),
            )
            .group_by(ChatAudioTrack.chat_id)
        )
    ).all()
    counts = {int(cid): int(cnt) for cid, cnt in count_rows}

    bot_rows = (
        await session.execute(select(BotGroupChat).where(BotGroupChat.chat_id.in_(allowed_ids)))
    ).scalars().all()
    row_by_id = {int(r.chat_id): r for r in bot_rows}

    chats: list[dict] = []
    for cid in allowed_ids:
        row = row_by_id.get(cid)
        title = (row.title if row and row.title else None) or f"Чат {cid}"
        chats.append(
            {
                "chat_id": cid,
                "title": title,
                "track_count": counts.get(cid, 0),
            }
        )
    chats.sort(key=lambda c: (str(c["title"]).casefold(), int(c["chat_id"])))
    return {"chats": chats}


async def list_tracks_for_player_chat(
    session: AsyncSession,
    player_id: int,
    chat_id: int,
    limit: int = 200,
) -> list[dict] | None:
    """Tracks from one chat; ``None`` if the player has no access to that chat."""
    allowed_ids = await _player_active_bot_chat_ids(session, player_id)
    cid = int(chat_id)
    if cid not in allowed_ids:
        return None
    stmt = (
        select(ChatAudioTrack)
        .where(
            ChatAudioTrack.chat_id == cid,
            ~ChatAudioTrack.file_unique_id.startswith("web:"),
        )
        .order_by(ChatAudioTrack.created_at.desc(), ChatAudioTrack.id.desc())
        .limit(int(limit))
    )
    rows = list((await session.execute(stmt)).scalars().all())
    return [_track_dict(t) for t in rows]


async def list_tracks_for_player(session: AsyncSession, player_id: int, limit: int = 50) -> list[dict]:
    """Tracks from every group chat the player belongs to, newest first."""
    chat_ids = await resolve_player_group_chats(session, player_id)
    if not chat_ids:
        return []
    stmt = (
        select(ChatAudioTrack)
        .where(
            ChatAudioTrack.chat_id.in_(chat_ids),
            ~ChatAudioTrack.file_unique_id.startswith("web:"),
        )
        .order_by(ChatAudioTrack.created_at.desc(), ChatAudioTrack.id.desc())
        .limit(int(limit))
    )
    rows = list((await session.execute(stmt)).scalars().all())
    return [_track_dict(t) for t in rows]


def _admin_track_dict(t: ChatAudioTrack) -> dict[str, Any]:
    out = _track_dict(t)
    out["relative_path"] = t.relative_path
    out["file_exists"] = (_static_root() / t.relative_path).is_file()
    out["created_at"] = t.created_at.isoformat() if t.created_at else None
    out["uploader_player_id"] = int(t.uploader_player_id) if t.uploader_player_id else None
    out["mime_type"] = t.mime_type
    out["file_size"] = t.file_size
    return out


def _events_last_hour_count() -> int:
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=1)
    count = 0
    for e in _TAVERN_AUDIO_EVENTS:
        try:
            ts = datetime.fromisoformat(e.ts)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= cutoff:
                count += 1
        except (TypeError, ValueError):
            continue
    return count


async def admin_bgm_overview(session: AsyncSession) -> dict[str, Any]:
    total_tracks = int(
        await session.scalar(select(func.count()).select_from(ChatAudioTrack)) or 0
    )
    chats_with_tracks = int(
        await session.scalar(select(func.count(func.distinct(ChatAudioTrack.chat_id)))) or 0
    )
    since_24h = datetime.now(tz=timezone.utc) - timedelta(hours=24)
    tracks_last_24h = int(
        await session.scalar(
            select(func.count()).select_from(ChatAudioTrack).where(ChatAudioTrack.created_at >= since_24h)
        )
        or 0
    )
    rows = list((await session.execute(select(ChatAudioTrack))).scalars().all())
    missing_files = sum(1 for t in rows if not (_static_root() / t.relative_path).is_file())
    pending_failed_count = int(
        await session.scalar(
            select(func.count())
            .select_from(ChatAudioCapturePending)
            .where(ChatAudioCapturePending.status == "failed")
        )
        or 0
    )
    return {
        "total_tracks": total_tracks,
        "chats_with_tracks": chats_with_tracks,
        "tracks_last_24h": tracks_last_24h,
        "missing_files": missing_files,
        "pending_failed_count": pending_failed_count,
        "events_last_hour": _events_last_hour_count(),
        "events_buffer_size": len(_TAVERN_AUDIO_EVENTS),
    }


def _admin_pending_dict(p: ChatAudioCapturePending) -> dict[str, Any]:
    return {
        "id": int(p.id),
        "chat_id": int(p.chat_id),
        "file_unique_id": p.file_unique_id,
        "file_id": p.file_id,
        "title": p.title,
        "performer": p.performer,
        "file_size": p.file_size,
        "mime_type": p.mime_type,
        "uploader_player_id": int(p.uploader_player_id) if p.uploader_player_id else None,
        "status": p.status,
        "last_error": p.last_error,
        "retry_count": int(p.retry_count or 0),
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


async def admin_bgm_pending(
    session: AsyncSession,
    *,
    chat_id: int | None = None,
    status: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    stmt = select(ChatAudioCapturePending).order_by(
        ChatAudioCapturePending.updated_at.desc(),
        ChatAudioCapturePending.id.desc(),
    )
    if chat_id is not None:
        stmt = stmt.where(ChatAudioCapturePending.chat_id == int(chat_id))
    status_clean = (status or "").strip().lower()
    if status_clean:
        stmt = stmt.where(ChatAudioCapturePending.status == status_clean)
    stmt = stmt.limit(max(1, min(int(limit), 200)))
    rows = list((await session.execute(stmt)).scalars().all())
    return {"items": [_admin_pending_dict(p) for p in rows]}


async def admin_bgm_chats(
    session: AsyncSession,
    *,
    q: str = "",
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    base = select(BotGroupChat)
    q_clean = q.strip()
    if q_clean:
        if q_clean.lstrip("-").isdigit():
            base = base.where(BotGroupChat.chat_id == int(q_clean))
        else:
            like = f"%{q_clean}%"
            base = base.where(
                or_(
                    BotGroupChat.title.ilike(like),
                    BotGroupChat.username.ilike(like),
                )
            )
    total = int(await session.scalar(select(func.count()).select_from(base.subquery())) or 0)
    offset = (page - 1) * page_size
    order = BotGroupChat.last_activity_at.desc().nullslast(), BotGroupChat.joined_at.desc()
    rows = (
        await session.execute(base.order_by(*order).offset(offset).limit(page_size))
    ).scalars().all()

    chat_ids = [int(r.chat_id) for r in rows]
    counts: dict[int, int] = {}
    last_at: dict[int, datetime | None] = {}
    if chat_ids:
        count_rows = (
            await session.execute(
                select(ChatAudioTrack.chat_id, func.count(ChatAudioTrack.id))
                .where(ChatAudioTrack.chat_id.in_(chat_ids))
                .group_by(ChatAudioTrack.chat_id)
            )
        ).all()
        counts = {int(cid): int(cnt) for cid, cnt in count_rows}
        last_rows = (
            await session.execute(
                select(ChatAudioTrack.chat_id, func.max(ChatAudioTrack.created_at))
                .where(ChatAudioTrack.chat_id.in_(chat_ids))
                .group_by(ChatAudioTrack.chat_id)
            )
        ).all()
        last_at = {int(cid): ts for cid, ts in last_rows}

    items: list[dict[str, Any]] = []
    for row in rows:
        cid = int(row.chat_id)
        items.append(
            {
                "chat_id": cid,
                "title": row.title,
                "username": row.username,
                "status": row.status,
                "track_count": counts.get(cid, 0),
                "last_track_at": last_at.get(cid).isoformat() if last_at.get(cid) else None,
            }
        )
    return {"total": total, "page": page, "page_size": page_size, "items": items}


async def admin_bgm_tracks(session: AsyncSession, chat_id: int) -> dict[str, Any]:
    cid = int(chat_id)
    rows = list(
        (
            await session.execute(
                select(ChatAudioTrack)
                .where(ChatAudioTrack.chat_id == cid)
                .order_by(ChatAudioTrack.created_at.desc(), ChatAudioTrack.id.desc())
            )
        ).scalars().all()
    )
    return {"chat_id": cid, "tracks": [_admin_track_dict(t) for t in rows]}


_REPEAT_MODES = frozenset({"off", "one", "all"})


def _normalize_repeat(value: str | None) -> str:
    repeat = str(value or "all").strip().lower()
    return repeat if repeat in _REPEAT_MODES else "all"


def _playlist_dict(p: PlayerBgmPlaylist, track_count: int = 0) -> dict[str, Any]:
    return {
        "id": int(p.id),
        "player_id": int(p.player_id),
        "chat_id": int(p.chat_id),
        "name": p.name,
        "shuffle": bool(p.shuffle),
        "repeat": _normalize_repeat(p.repeat),
        "track_count": int(track_count),
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


async def _get_player_playlist(
    session: AsyncSession, player_id: int, playlist_id: int
) -> PlayerBgmPlaylist | None:
    return await session.scalar(
        select(PlayerBgmPlaylist).where(
            PlayerBgmPlaylist.id == int(playlist_id),
            PlayerBgmPlaylist.player_id == int(player_id),
        )
    )


async def _ensure_chat_allowed(session: AsyncSession, player_id: int, chat_id: int) -> bool:
    allowed = await _player_active_bot_chat_ids(session, player_id)
    return int(chat_id) in allowed


async def _get_or_create_prefs(session: AsyncSession, player_id: int) -> PlayerBgmPrefs:
    prefs = await session.get(PlayerBgmPrefs, int(player_id))
    if prefs is None:
        prefs = PlayerBgmPrefs(player_id=int(player_id), active_playlist_id=None)
        session.add(prefs)
        await session.flush()
    return prefs


async def list_playlists_for_player(session: AsyncSession, player_id: int) -> dict[str, Any]:
    pid = int(player_id)
    count_rows = (
        await session.execute(
            select(PlayerBgmPlaylistTrack.playlist_id, func.count(PlayerBgmPlaylistTrack.id))
            .join(PlayerBgmPlaylist, PlayerBgmPlaylist.id == PlayerBgmPlaylistTrack.playlist_id)
            .where(PlayerBgmPlaylist.player_id == pid)
            .group_by(PlayerBgmPlaylistTrack.playlist_id)
        )
    ).all()
    counts = {int(r[0]): int(r[1]) for r in count_rows}

    rows = list(
        (
            await session.execute(
                select(PlayerBgmPlaylist)
                .where(PlayerBgmPlaylist.player_id == pid)
                .order_by(PlayerBgmPlaylist.updated_at.desc(), PlayerBgmPlaylist.id.desc())
            )
        ).scalars().all()
    )
    prefs = await session.get(PlayerBgmPrefs, pid)
    active_id = int(prefs.active_playlist_id) if prefs and prefs.active_playlist_id else None
    return {
        "playlists": [_playlist_dict(p, counts.get(int(p.id), 0)) for p in rows],
        "active_playlist_id": active_id,
    }


async def create_playlist(
    session: AsyncSession,
    player_id: int,
    chat_id: int,
    name: str,
) -> dict[str, Any] | None:
    pid = int(player_id)
    cid = int(chat_id)
    if not await _ensure_chat_allowed(session, pid, cid):
        return None
    clean_name = str(name or "").strip()[:128] or "Новый плейлист"
    playlist = PlayerBgmPlaylist(
        player_id=pid,
        chat_id=cid,
        name=clean_name,
        shuffle=False,
        repeat="all",
    )
    session.add(playlist)
    await session.commit()
    await session.refresh(playlist)
    return _playlist_dict(playlist, 0)


async def update_playlist(
    session: AsyncSession,
    player_id: int,
    playlist_id: int,
    *,
    name: str | None = None,
    shuffle: bool | None = None,
    repeat: str | None = None,
) -> dict[str, Any] | None:
    playlist = await _get_player_playlist(session, player_id, playlist_id)
    if playlist is None:
        return None
    if name is not None:
        clean = str(name).strip()[:128]
        if clean:
            playlist.name = clean
    if shuffle is not None:
        playlist.shuffle = bool(shuffle)
    if repeat is not None:
        playlist.repeat = _normalize_repeat(repeat)
    await session.commit()
    await session.refresh(playlist)
    count = await session.scalar(
        select(func.count(PlayerBgmPlaylistTrack.id)).where(
            PlayerBgmPlaylistTrack.playlist_id == int(playlist.id)
        )
    )
    return _playlist_dict(playlist, int(count or 0))


async def delete_playlist(session: AsyncSession, player_id: int, playlist_id: int) -> bool:
    playlist = await _get_player_playlist(session, player_id, playlist_id)
    if playlist is None:
        return False
    prefs = await session.get(PlayerBgmPrefs, int(player_id))
    if prefs and prefs.active_playlist_id == int(playlist.id):
        prefs.active_playlist_id = None
    await session.delete(playlist)
    await session.commit()
    return True


async def get_playlist_with_tracks(
    session: AsyncSession, player_id: int, playlist_id: int
) -> dict[str, Any] | None:
    playlist = await _get_player_playlist(session, player_id, playlist_id)
    if playlist is None:
        return None
    rows = list(
        (
            await session.execute(
                select(ChatAudioTrack, PlayerBgmPlaylistTrack.position)
                .join(
                    PlayerBgmPlaylistTrack,
                    PlayerBgmPlaylistTrack.track_id == ChatAudioTrack.id,
                )
                .where(PlayerBgmPlaylistTrack.playlist_id == int(playlist.id))
                .order_by(PlayerBgmPlaylistTrack.position.asc(), PlayerBgmPlaylistTrack.id.asc())
            )
        ).all()
    )
    tracks = [_track_dict(t) for t, _pos in rows]
    out = _playlist_dict(playlist, len(tracks))
    out["tracks"] = tracks
    return out


async def _validate_track_for_playlist(
    session: AsyncSession, playlist: PlayerBgmPlaylist, track_id: int
) -> ChatAudioTrack | None:
    track = await session.get(ChatAudioTrack, int(track_id))
    if track is None:
        return None
    if int(track.chat_id) != int(playlist.chat_id):
        return None
    return track


async def set_playlist_tracks(
    session: AsyncSession,
    player_id: int,
    playlist_id: int,
    track_ids: list[int],
) -> dict[str, Any] | None:
    playlist = await _get_player_playlist(session, player_id, playlist_id)
    if playlist is None:
        return None
    seen: set[int] = set()
    ordered: list[int] = []
    for raw in track_ids:
        tid = int(raw)
        if tid in seen:
            continue
        track = await _validate_track_for_playlist(session, playlist, tid)
        if track is None:
            return None
        seen.add(tid)
        ordered.append(tid)

    await session.execute(
        delete(PlayerBgmPlaylistTrack).where(
            PlayerBgmPlaylistTrack.playlist_id == int(playlist.id)
        )
    )
    for pos, tid in enumerate(ordered):
        session.add(
            PlayerBgmPlaylistTrack(
                playlist_id=int(playlist.id),
                track_id=int(tid),
                position=pos,
            )
        )
    await session.commit()
    return await get_playlist_with_tracks(session, player_id, playlist_id)


async def add_track_to_playlist(
    session: AsyncSession,
    player_id: int,
    playlist_id: int,
    track_id: int,
) -> dict[str, Any] | None:
    playlist = await _get_player_playlist(session, player_id, playlist_id)
    if playlist is None:
        return None
    track = await _validate_track_for_playlist(session, playlist, track_id)
    if track is None:
        return None
    existing = await session.scalar(
        select(PlayerBgmPlaylistTrack.id).where(
            PlayerBgmPlaylistTrack.playlist_id == int(playlist.id),
            PlayerBgmPlaylistTrack.track_id == int(track_id),
        )
    )
    if existing:
        return await get_playlist_with_tracks(session, player_id, playlist_id)

    max_pos = await session.scalar(
        select(func.max(PlayerBgmPlaylistTrack.position)).where(
            PlayerBgmPlaylistTrack.playlist_id == int(playlist.id)
        )
    )
    next_pos = int(max_pos) + 1 if max_pos is not None else 0
    session.add(
        PlayerBgmPlaylistTrack(
            playlist_id=int(playlist.id),
            track_id=int(track_id),
            position=next_pos,
        )
    )
    await session.commit()
    return await get_playlist_with_tracks(session, player_id, playlist_id)


async def remove_track_from_playlist(
    session: AsyncSession,
    player_id: int,
    playlist_id: int,
    track_id: int,
) -> dict[str, Any] | None:
    playlist = await _get_player_playlist(session, player_id, playlist_id)
    if playlist is None:
        return None
    row = await session.scalar(
        select(PlayerBgmPlaylistTrack).where(
            PlayerBgmPlaylistTrack.playlist_id == int(playlist.id),
            PlayerBgmPlaylistTrack.track_id == int(track_id),
        )
    )
    if row is None:
        return await get_playlist_with_tracks(session, player_id, playlist_id)
    removed_pos = int(row.position)
    await session.delete(row)
    await session.flush()
    later_rows = list(
        (
            await session.execute(
                select(PlayerBgmPlaylistTrack)
                .where(
                    PlayerBgmPlaylistTrack.playlist_id == int(playlist.id),
                    PlayerBgmPlaylistTrack.position > removed_pos,
                )
                .order_by(PlayerBgmPlaylistTrack.position.asc())
            )
        ).scalars().all()
    )
    for r in later_rows:
        r.position = int(r.position) - 1
    await session.commit()
    return await get_playlist_with_tracks(session, player_id, playlist_id)


async def set_active_playlist(
    session: AsyncSession, player_id: int, playlist_id: int
) -> dict[str, Any] | None:
    playlist = await _get_player_playlist(session, player_id, playlist_id)
    if playlist is None:
        return None
    prefs = await _get_or_create_prefs(session, player_id)
    prefs.active_playlist_id = int(playlist.id)
    await session.commit()
    return await get_playlist_with_tracks(session, player_id, playlist_id)


async def get_active_playlist(
    session: AsyncSession, player_id: int
) -> dict[str, Any] | None:
    prefs = await session.get(PlayerBgmPrefs, int(player_id))
    if not prefs or not prefs.active_playlist_id:
        return None
    return await get_playlist_with_tracks(session, player_id, int(prefs.active_playlist_id))


async def upload_chat_audio_from_web(
    session: AsyncSession,
    player_id: int,
    chat_id: int,
    raw: bytes,
    file_name: str | None,
    mime_type: str | None,
    duration: int | None = None,
) -> dict[str, Any]:
    """Upload an audio file from the webapp into a group chat track library."""
    pid = int(player_id)
    cid = int(chat_id)
    if not await _ensure_chat_allowed(session, pid, cid):
        raise ValueError("chat_not_allowed")
    if not raw:
        raise ValueError("empty_file")
    if len(raw) > MAX_AUDIO_BYTES:
        raise ValueError("file_too_large")
    if not (_is_audio_mime(mime_type) or _is_audio_file_name(file_name)):
        raise ValueError("invalid_audio_type")

    digest = hashlib.sha256(raw).hexdigest()
    file_unique_id = f"web:{digest[:64]}"
    existing = await session.scalar(
        select(ChatAudioTrack.id).where(ChatAudioTrack.file_unique_id == file_unique_id)
    )
    if existing:
        track = await session.get(ChatAudioTrack, int(existing))
        if track:
            return {"ok": True, "status": "dedupe", "track": _track_dict(track)}

    ext = _ext_for_audio(file_name, mime_type)
    uid_part = _safe_component(digest[:16], "upload")
    rel_dir = f"game/tavern_tracks/{_safe_component(str(cid), 'chat')}"
    rel_path = f"{rel_dir}/{uid_part}{ext}"
    dest = _static_root() / rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)

    title = _title_from_file_name(file_name)
    track = ChatAudioTrack(
        chat_id=cid,
        file_unique_id=file_unique_id,
        file_id=f"web_upload:{uuid.uuid4().hex}",
        relative_path=rel_path,
        title=title,
        performer=None,
        duration=int(duration) if duration is not None and int(duration) > 0 else None,
        mime_type=(mime_type or "").strip() or None,
        file_size=len(raw),
        uploader_player_id=pid,
    )
    session.add(track)
    await session.commit()
    await session.refresh(track)
    log_tavern_audio_event(
        "web_upload",
        chat_id=cid,
        player_id=pid,
        detail=f"track_id={track.id} bytes={len(raw)} path={rel_path}",
    )
    return {"ok": True, "status": "cached", "track": _track_dict(track)}


async def admin_bgm_player_preview(session: AsyncSession, player_id: int) -> dict[str, Any]:
    pid = int(player_id)
    player_group_chats = await resolve_player_group_chats(session, pid)
    bot_active = await _player_active_bot_chat_ids(session, pid)
    player_view = await list_bgm_chats_for_player(session, pid)
    return {
        "player_id": pid,
        "player_group_chats": player_group_chats,
        "bot_active_intersection": bot_active,
        "player_view": player_view,
    }
