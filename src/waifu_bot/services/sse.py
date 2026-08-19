"""Server-Sent Events helper using Redis pub/sub."""
import asyncio
import contextlib
import logging
from typing import AsyncIterator

from fastapi.responses import StreamingResponse
from redis.asyncio.client import Redis
from starlette.middleware.gzip import GZipMiddleware

logger = logging.getLogger(__name__)

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
    "Content-Encoding": "identity",
    "Content-Type": "text/event-stream",
}


class SseSkipGZipMiddleware:
    """Gzip HTTP responses except /api/sse — EventSource frames must not sit in zlib.

    This *is* the gzip middleware (not a wrapper nested inside GZipResponder).
    SSE paths call the inner app directly; everything else goes through gzip.
    """

    def __init__(self, app, minimum_size: int = 500):
        self.app = app
        self.gzip = GZipMiddleware(app, minimum_size=minimum_size)

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            path = scope.get("path") or ""
            if str(path).startswith("/api/sse"):
                await self.app(scope, receive, send)
                return
        await self.gzip(scope, receive, send)


def _message_data_text(data) -> str | None:
    if data is None or data == "":
        return None
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return str(data)


async def event_stream(redis: Redis, channel: str, heartbeat: float = 15.0) -> AsyncIterator[str]:
    """SSE event stream for a given Redis pubsub channel.

    Subscribe first, then emit the SSE preamble so a hit published between
    subscribe and the first yield is still delivered.
    """
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)
    queue: asyncio.Queue[str] = asyncio.Queue()
    stop = asyncio.Event()

    async def _listen() -> None:
        try:
            async for message in pubsub.listen():
                if stop.is_set():
                    return
                if not message or message.get("type") != "message":
                    continue
                text = _message_data_text(message.get("data"))
                if text is None:
                    continue
                await queue.put(f"data: {text}\n\n")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("SSE listen failed channel=%s", channel)

    async def _heartbeat() -> None:
        try:
            while not stop.is_set():
                await asyncio.sleep(heartbeat)
                await queue.put(": ping\n\n")
        except asyncio.CancelledError:
            raise

    listen_task = asyncio.create_task(_listen(), name=f"sse-listen:{channel}")
    hb_task = asyncio.create_task(_heartbeat(), name=f"sse-hb:{channel}")
    try:
        yield "retry: 3000\n\n: connected\n\n"
        while True:
            chunk = await queue.get()
            yield chunk
    finally:
        stop.set()
        listen_task.cancel()
        hb_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await listen_task
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await hb_task
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(channel)
        with contextlib.suppress(Exception):
            await pubsub.close()


def sse_response(redis: Redis, channel: str) -> StreamingResponse:
    """Return streaming response for SSE channel (never gzip)."""
    return StreamingResponse(
        event_stream(redis, channel),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


async def publish_event(redis: Redis, player_id: int, payload: dict) -> None:
    """Publish event to player's SSE channel."""
    channel = f"sse:{player_id}"
    await redis.publish(channel, json_dumps(payload))


def json_dumps(payload: dict) -> str:
    """Serialize payload to JSON string."""
    import json

    return json.dumps(payload, ensure_ascii=False)
