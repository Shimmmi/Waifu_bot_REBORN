"""Unit tests for tavern group-chat audio capture (audio + document attachments)."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from waifu_bot.services.tavern_audio import (
    TelegramFileDownloadError,
    _audio_attachment_from_message,
    _download_telegram_file,
    _httpx_download_timeout,
    _stream_file_url,
    admin_bgm_overview,
    admin_bgm_pending,
    capture_chat_audio_attachment,
    clear_tavern_audio_events_for_tests,
    list_recent_tavern_audio_events,
    log_tavern_audio_event,
    log_tavern_audio_reject_document,
    message_has_tavern_audio,
    retry_pending_capture,
    save_chat_audio_from_message,
)


def _message(**kwargs):
    base = {
        "chat": SimpleNamespace(id=-100111),
        "from_user": SimpleNamespace(id=42),
        "audio": None,
        "document": None,
        "voice": None,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def _mock_bot(file_path: str = "documents/file.mp3") -> AsyncMock:
    bot = AsyncMock()
    bot.token = "123:test"
    bot.session.api.file_url = MagicMock(
        return_value=f"https://worker.example/file/bot123:test/{file_path}"
    )
    bot.get_file = AsyncMock(return_value=SimpleNamespace(file_path=file_path))
    return bot


def test_audio_attachment_from_message_audio():
    msg = _message(
        audio=SimpleNamespace(
            file_id="audio_fid",
            file_unique_id="audio_uid",
            file_name="song.mp3",
            mime_type="audio/mpeg",
            file_size=1234,
            title="My Song",
            performer="Artist",
            duration=180,
        )
    )
    att = _audio_attachment_from_message(msg)
    assert att is not None
    assert att["file_id"] == "audio_fid"
    assert att["file_unique_id"] == "audio_uid"
    assert att["title"] == "My Song"
    assert att["performer"] == "Artist"
    assert att["duration"] == 180


def test_audio_attachment_from_document_mime():
    msg = _message(
        document=SimpleNamespace(
            file_id="doc_fid",
            file_unique_id="doc_uid",
            file_name="track.bin",
            mime_type="audio/mpeg",
            file_size=5678,
        )
    )
    att = _audio_attachment_from_message(msg)
    assert att is not None
    assert att["file_id"] == "doc_fid"
    assert att["title"] == "track"


def test_audio_attachment_from_document_extension():
    msg = _message(
        document=SimpleNamespace(
            file_id="doc_fid2",
            file_unique_id="doc_uid2",
            file_name="mixtape.mp3",
            mime_type="application/octet-stream",
            file_size=999,
        )
    )
    att = _audio_attachment_from_message(msg)
    assert att is not None
    assert att["title"] == "mixtape"


def test_audio_attachment_rejects_pdf_and_voice():
    pdf_msg = _message(
        document=SimpleNamespace(
            file_id="pdf_fid",
            file_unique_id="pdf_uid",
            file_name="readme.pdf",
            mime_type="application/pdf",
            file_size=100,
        )
    )
    assert _audio_attachment_from_message(pdf_msg) is None
    assert message_has_tavern_audio(pdf_msg) is False

    voice_msg = _message(
        voice=SimpleNamespace(
            file_id="voice_fid",
            file_unique_id="voice_uid",
            file_size=100,
        )
    )
    assert _audio_attachment_from_message(voice_msg) is None


def test_save_chat_audio_from_document_writes_track():
    async def _run(tmp_path):
        msg = _message(
            document=SimpleNamespace(
                file_id="doc_fid",
                file_unique_id="doc_uid",
                file_name="upload.mp3",
                mime_type="audio/mpeg",
                file_size=4,
            )
        )
        bot = _mock_bot()

        session = AsyncMock()
        session.scalar = AsyncMock(return_value=None)
        session.add = MagicMock()
        session.commit = AsyncMock()

        async def _refresh(track):
            track.id = 99

        session.refresh = AsyncMock(side_effect=_refresh)

        async def _session_gen():
            yield session

        clear_tavern_audio_events_for_tests()
        with patch("waifu_bot.services.tavern_audio.get_session", _session_gen), patch(
            "waifu_bot.services.tavern_audio._static_root", return_value=tmp_path
        ), patch(
            "waifu_bot.services.tavern_audio._download_telegram_file",
            new=AsyncMock(return_value=b"test"),
        ), patch(
            "waifu_bot.services.tavern_audio._upsert_pending_capture",
            new=AsyncMock(),
        ), patch(
            "waifu_bot.services.tavern_audio._delete_pending_capture",
            new=AsyncMock(),
        ):
            await save_chat_audio_from_message(bot, msg)

        from waifu_bot.db.models import ChatAudioTrack

        track_calls = [c[0][0] for c in session.add.call_args_list if isinstance(c[0][0], ChatAudioTrack)]
        assert len(track_calls) == 1
        track = track_calls[0]
        assert track.chat_id == -100111
        assert track.file_unique_id == "doc_uid"
        assert track.title == "upload"
        assert track.mime_type == "audio/mpeg"
        dest = tmp_path / track.relative_path
        assert dest.is_file()
        assert dest.read_bytes() == b"test"
        events = list_recent_tavern_audio_events(10)
        assert any(e["event"] == "cached" for e in events)

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(_run(Path(tmp)))


def test_httpx_download_timeout_uses_read_not_total():
    with patch("waifu_bot.services.tavern_audio.settings") as mock_settings:
        mock_settings.telegram_file_download_read_timeout = 45
        timeout = _httpx_download_timeout()
    assert timeout.read == 45.0
    assert timeout.connect == 30.0


def test_stream_file_url_slow_stream_completes():
    async def _run():
        chunk_count = 80
        payload = b"x" * 1024

        class FakeResponse:
            def raise_for_status(self) -> None:
                return None

            async def aiter_bytes(self, _chunk_size: int):
                for _ in range(chunk_count):
                    yield payload

        class FakeStream:
            async def __aenter__(self):
                return FakeResponse()

            async def __aexit__(self, *_args):
                return None

        class FakeClient:
            def stream(self, _method: str, _url: str):
                return FakeStream()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

        captured_timeout = {}

        def _client_factory(*_args, timeout=None, **_kwargs):
            captured_timeout["value"] = timeout
            return FakeClient()

        with patch("waifu_bot.services.tavern_audio.httpx.AsyncClient", side_effect=_client_factory):
            raw = await _stream_file_url("https://worker.example/file/bot123:test/doc")

        assert len(raw) == chunk_count * len(payload)
        assert captured_timeout["value"].read == _httpx_download_timeout().read

    asyncio.run(_run())


def test_download_telegram_file_retries_after_read_timeout():
    async def _run():
        bot = _mock_bot()
        calls = {"n": 0}

        async def _stream(url: str) -> bytes:
            calls["n"] += 1
            if calls["n"] == 1:
                raise httpx.ReadTimeout("stall")
            return b"ok"

        clear_tavern_audio_events_for_tests()
        with patch("waifu_bot.services.tavern_audio._stream_file_url", side_effect=_stream), patch(
            "waifu_bot.services.tavern_audio.asyncio.sleep", new=AsyncMock()
        ):
            raw = await _download_telegram_file(
                bot,
                "file_id",
                chat_id=-100,
                player_id=1,
                expected_bytes=999,
            )

        assert raw == b"ok"
        assert calls["n"] == 2
        events = list_recent_tavern_audio_events(10)
        assert any(e["event"] == "download" for e in events)
        assert any(e["event"] == "download_retry" for e in events)

    asyncio.run(_run())


def test_save_chat_audio_retries_download_and_caches():
    async def _run(tmp_path):
        msg = _message(
            document=SimpleNamespace(
                file_id="doc_fid",
                file_unique_id="doc_uid",
                file_name="upload.mp3",
                mime_type="audio/mpeg",
                file_size=4,
            )
        )
        bot = _mock_bot()
        calls = {"n": 0}

        async def _stream(_url: str) -> bytes:
            calls["n"] += 1
            if calls["n"] == 1:
                raise httpx.ReadTimeout("stall")
            return b"test"

        session = AsyncMock()
        session.scalar = AsyncMock(return_value=None)
        session.add = MagicMock()
        session.commit = AsyncMock()

        async def _refresh(track):
            track.id = 99

        session.refresh = AsyncMock(side_effect=_refresh)

        session_calls = {"n": 0}

        async def _session_gen():
            session_calls["n"] += 1
            yield session

        clear_tavern_audio_events_for_tests()
        with patch("waifu_bot.services.tavern_audio.get_session", _session_gen), patch(
            "waifu_bot.services.tavern_audio._static_root", return_value=tmp_path
        ), patch(
            "waifu_bot.services.tavern_audio._stream_file_url", side_effect=_stream
        ), patch("waifu_bot.services.tavern_audio.asyncio.sleep", new=AsyncMock()):
            await save_chat_audio_from_message(bot, msg)

        events = list_recent_tavern_audio_events(10)
        assert any(e["event"] == "cached" for e in events)
        assert not any(e["event"] == "failed" for e in events)
        assert calls["n"] == 2
        assert session_calls["n"] == 3

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(_run(Path(tmp)))


def test_db_session_not_held_during_download():
    async def _run(tmp_path):
        msg = _message(
            document=SimpleNamespace(
                file_id="doc_fid",
                file_unique_id="doc_uid",
                file_name="upload.mp3",
                mime_type="audio/mpeg",
                file_size=4,
            )
        )
        bot = _mock_bot()
        phases: list[str] = []
        download_started = asyncio.Event()
        download_can_finish = asyncio.Event()

        async def _download(_bot, _file_id, **_kwargs):
            phases.append("download_running")
            download_started.set()
            await download_can_finish.wait()
            return b"payload"

        def _make_session(label: str):
            session = AsyncMock()
            session.scalar = AsyncMock(return_value=None)
            session.add = MagicMock()
            session.commit = AsyncMock()

            async def _refresh(track):
                track.id = 99

            session.refresh = AsyncMock(side_effect=_refresh)

            async def _session_gen():
                phases.append(f"{label}_open")
                try:
                    yield session
                finally:
                    phases.append(f"{label}_close")

            return _session_gen

        session_calls = {"n": 0}

        def _session_router():
            session_calls["n"] += 1
            if session_calls["n"] == 1:
                return _make_session("dedupe")()
            if session_calls["n"] == 2:
                return _make_session("pending")()
            return _make_session("persist")()

        clear_tavern_audio_events_for_tests()
        with patch("waifu_bot.services.tavern_audio.get_session", _session_router), patch(
            "waifu_bot.services.tavern_audio._static_root", return_value=tmp_path
        ), patch(
            "waifu_bot.services.tavern_audio._download_telegram_file", side_effect=_download
        ):
            task = asyncio.create_task(save_chat_audio_from_message(bot, msg))
            await asyncio.wait_for(download_started.wait(), timeout=1.0)
            assert "dedupe_close" in phases
            assert "pending_close" in phases
            assert "download_running" in phases
            assert "persist_open" not in phases
            download_can_finish.set()
            await task

        assert "persist_open" in phases
        assert phases.index("pending_close") < phases.index("download_running")
        assert phases.index("download_running") < phases.index("persist_open")

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(_run(Path(tmp)))


def test_log_tavern_audio_event_ring_buffer():
    clear_tavern_audio_events_for_tests()
    log_tavern_audio_event("enqueue", chat_id=-100, player_id=1, detail="kind=document")
    events = list_recent_tavern_audio_events(5)
    assert len(events) == 1
    assert events[0]["event"] == "enqueue"
    assert events[0]["chat_id"] == -100


def test_log_tavern_audio_reject_document_for_pdf():
    clear_tavern_audio_events_for_tests()
    msg = _message(
        document=SimpleNamespace(
            file_id="pdf_fid",
            file_unique_id="pdf_uid",
            file_name="readme.pdf",
            mime_type="application/pdf",
            file_size=100,
        )
    )
    log_tavern_audio_reject_document(msg, -100111, 42)
    events = list_recent_tavern_audio_events(5)
    assert len(events) == 1
    assert events[0]["event"] == "reject_document"


def test_admin_bgm_overview_counts():
    async def _run():
        session = AsyncMock()
        session.scalar = AsyncMock(side_effect=[5, 2, 1, 3])
        session.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=lambda: [])))
        )
        out = await admin_bgm_overview(session)
        assert out["total_tracks"] == 5
        assert out["chats_with_tracks"] == 2
        assert out["tracks_last_24h"] == 1
        assert out["missing_files"] == 0
        assert out["pending_failed_count"] == 3

    asyncio.run(_run())


def _attachment(**kwargs):
    base = {
        "file_id": "doc_fid",
        "file_unique_id": "doc_uid",
        "file_name": "upload.mp3",
        "mime_type": "audio/mpeg",
        "file_size": 4,
        "title": "upload",
        "performer": None,
        "duration": None,
    }
    base.update(kwargs)
    return base


def test_capture_upserts_pending_before_download():
    async def _run():
        bot = _mock_bot()
        pending_added = False

        async def _upsert(session, attachment, **kwargs):
            nonlocal pending_added
            pending_added = True
            assert attachment["file_unique_id"] == "doc_uid"

        with patch(
            "waifu_bot.services.tavern_audio._upsert_pending_capture",
            side_effect=_upsert,
        ), patch(
            "waifu_bot.services.tavern_audio._download_telegram_file",
            new=AsyncMock(return_value=b"data"),
        ), patch(
            "waifu_bot.services.tavern_audio.get_session",
        ) as mock_get_session:
            session = AsyncMock()
            session.scalar = AsyncMock(return_value=None)
            session.add = MagicMock()
            session.commit = AsyncMock()
            session.refresh = AsyncMock(side_effect=lambda t: setattr(t, "id", 1))
            session.delete = AsyncMock()

            async def _gen():
                yield session

            mock_get_session.side_effect = lambda: _gen()
            with patch("waifu_bot.services.tavern_audio._static_root") as mock_root:
                mock_root.return_value = MagicMock()
                mock_root.return_value.__truediv__ = MagicMock(return_value=MagicMock(
                    parent=MagicMock(mkdir=MagicMock()),
                    write_bytes=MagicMock(),
                ))
                await capture_chat_audio_attachment(
                    bot,
                    _attachment(),
                    chat_id=-100111,
                    player_id=42,
                )
        assert pending_added

    asyncio.run(_run())


def test_capture_failed_marks_pending():
    async def _run():
        bot = _mock_bot()
        marked = False

        async def _mark(session, uid, exc, **kwargs):
            nonlocal marked
            marked = True
            assert uid == "doc_uid"

        with patch(
            "waifu_bot.services.tavern_audio._upsert_pending_capture",
            new=AsyncMock(),
        ), patch(
            "waifu_bot.services.tavern_audio._download_telegram_file",
            new=AsyncMock(side_effect=httpx.ReadTimeout("stall")),
        ), patch(
            "waifu_bot.services.tavern_audio._mark_pending_failed",
            side_effect=_mark,
        ), patch(
            "waifu_bot.services.tavern_audio.get_session",
        ) as mock_get_session:
            session = AsyncMock()
            session.scalar = AsyncMock(return_value=None)

            async def _gen():
                yield session

            mock_get_session.side_effect = lambda: _gen()
            with patch("waifu_bot.services.tavern_audio.asyncio.sleep", new=AsyncMock()):
                result = await capture_chat_audio_attachment(
                    bot,
                    _attachment(),
                    chat_id=-100111,
                    player_id=42,
                )
        assert marked
        assert result["ok"] is False
        assert result["status"] == "failed"

    asyncio.run(_run())


def test_retry_pending_capture_without_message():
    async def _run():
        bot = _mock_bot()
        pending = SimpleNamespace(
            chat_id=-100111,
            file_unique_id="doc_uid",
            file_id="doc_fid",
            file_name="upload.mp3",
            mime_type="audio/mpeg",
            file_size=4,
            title="upload",
            performer=None,
            duration=None,
            uploader_player_id=42,
            retry_count=1,
        )

        async def _gen():
            session = AsyncMock()
            session.scalar = AsyncMock(return_value=pending)
            yield session

        clear_tavern_audio_events_for_tests()
        with patch("waifu_bot.services.tavern_audio.get_session", _gen), patch(
            "waifu_bot.services.tavern_audio.capture_chat_audio_attachment",
            new=AsyncMock(return_value={"ok": True, "status": "cached", "track_id": 9}),
        ) as mock_capture:
            result = await retry_pending_capture(bot, "doc_uid")

        assert result["ok"] is True
        assert result["track_id"] == 9
        mock_capture.assert_awaited_once()
        events = list_recent_tavern_audio_events(5)
        assert any(e["event"] == "retry_manual" for e in events)

    asyncio.run(_run())


def test_admin_bgm_pending_list():
    async def _run():
        session = AsyncMock()
        row = SimpleNamespace(
            id=1,
            chat_id=-100111,
            file_unique_id="uid1",
            file_id="fid1",
            title="Song",
            performer=None,
            file_size=100,
            mime_type="audio/mpeg",
            uploader_player_id=42,
            status="failed",
            last_error="ReadTimeout",
            retry_count=2,
            created_at=SimpleNamespace(isoformat=lambda: "2026-01-01T00:00:00+00:00"),
            updated_at=SimpleNamespace(isoformat=lambda: "2026-01-01T01:00:00+00:00"),
        )
        session.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=lambda: [row])))
        )
        out = await admin_bgm_pending(session, status="failed")
        assert len(out["items"]) == 1
        assert out["items"][0]["file_unique_id"] == "uid1"
        assert out["items"][0]["status"] == "failed"

    asyncio.run(_run())
