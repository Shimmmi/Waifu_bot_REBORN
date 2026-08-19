"""SSE must not be gzipped and must deliver a published event immediately."""
from __future__ import annotations

import asyncio
import json

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from waifu_bot.services.sse import SseSkipGZipMiddleware
from waifu_bot.services import sse as sse_service


class FakePubSub:
    def __init__(self) -> None:
        self.queue: asyncio.Queue = asyncio.Queue()
        self.subscribed = asyncio.Event()

    async def subscribe(self, channel: str) -> None:
        self.subscribed.set()

    async def listen(self):
        yield {"type": "subscribe", "data": 1, "channel": "sse:1"}
        while True:
            data = await self.queue.get()
            yield {"type": "message", "data": data, "channel": "sse:1"}

    async def unsubscribe(self, channel: str) -> None:
        return None

    async def close(self) -> None:
        return None


class FakeRedis:
    def __init__(self) -> None:
        self.pubsub_obj = FakePubSub()

    def pubsub(self):
        return self.pubsub_obj

    async def publish(self, channel: str, payload: str) -> int:
        await self.pubsub_obj.queue.put(payload)
        return 1


def _sse_app(redis: FakeRedis) -> FastAPI:
    app = FastAPI()
    app.add_middleware(SseSkipGZipMiddleware, minimum_size=10)

    @app.get("/api/sse/stream")
    async def stream():
        return sse_service.sse_response(redis, "sse:1")

    @app.get("/api/ping-json")
    async def ping_json():
        return {"ok": True, "pad": "x" * 600}

    return app


def test_sse_stream_not_gzipped_and_delivers_event_under_200ms():
    async def _run():
        redis = FakeRedis()
        app = _sse_app(redis)
        started = asyncio.Event()
        headers: dict[str, str] = {}
        chunks: asyncio.Queue[bytes] = asyncio.Queue()

        async def receive():
            await asyncio.Event().wait()
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.start":
                for key, value in message.get("headers") or []:
                    headers[key.decode().lower()] = value.decode()
                started.set()
            elif message["type"] == "http.response.body":
                await chunks.put(message.get("body") or b"")

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/sse/stream",
            "raw_path": b"/api/sse/stream",
            "root_path": "",
            "query_string": b"",
            "headers": [(b"accept-encoding", b"gzip"), (b"host", b"test")],
            "client": ("127.0.0.1", 123),
            "server": ("test", 80),
        }
        task = asyncio.create_task(app(scope, receive, send))
        await asyncio.wait_for(started.wait(), timeout=1.0)
        encoding = (headers.get("content-encoding") or "").lower()
        assert encoding not in ("gzip", "deflate", "br"), headers
        assert "text/event-stream" in (headers.get("content-type") or "")
        assert headers.get("x-accel-buffering", "").lower() == "no"

        buf = b""
        deadline = asyncio.get_running_loop().time() + 1.0
        while b": connected" not in buf and b"retry:" not in buf:
            if asyncio.get_running_loop().time() > deadline:
                raise AssertionError(f"no SSE preamble: {buf!r}")
            buf += await asyncio.wait_for(chunks.get(), timeout=0.5)

        payload = {"type": "battle", "payload": {"dungeon_id": 1, "position": 1, "monster_hp": 1}}
        t0 = asyncio.get_running_loop().time()
        await redis.publish("sse:1", json.dumps(payload, ensure_ascii=False))
        while b"monster_hp" not in buf:
            if asyncio.get_running_loop().time() - t0 > 0.2:
                raise AssertionError(f"event not flushed in 200ms: {buf!r}")
            buf += await asyncio.wait_for(chunks.get(), timeout=0.2)
        elapsed_ms = (asyncio.get_running_loop().time() - t0) * 1000
        assert elapsed_ms < 200, elapsed_ms
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    asyncio.run(asyncio.wait_for(_run(), timeout=3))


def test_non_sse_json_still_gzipped():
    async def _run():
        redis = FakeRedis()
        app = _sse_app(redis)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/api/ping-json", headers={"Accept-Encoding": "gzip"})
            assert r.status_code == 200
            assert (r.headers.get("content-encoding") or "").lower() == "gzip"

    asyncio.run(_run())
