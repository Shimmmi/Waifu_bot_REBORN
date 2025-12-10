"""Server-Sent Events helper using Redis pub/sub."""
import asyncio
from datetime import datetime, timedelta
from typing import AsyncIterator, Optional

from fastapi.responses import StreamingResponse
from redis.asyncio.client import Redis


async def event_stream(redis: Redis, channel: str, heartbeat: float = 15.0) -> AsyncIterator[str]:
    """SSE event stream for a given Redis pubsub channel."""
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)

    last_sent = datetime.utcnow()

    try:
        while True:
            # Heartbeat
            now = datetime.utcnow()
            if (now - last_sent) > timedelta(seconds=heartbeat):
                yield "event: ping\ndata: {}\n\n"
                last_sent = now

            # Wait for message or timeout
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message.get("data"):
                yield f"data: {message['data']}\n\n"
                last_sent = datetime.utcnow()
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()


def sse_response(redis: Redis, channel: str) -> StreamingResponse:
    """Return streaming response for SSE channel."""
    return StreamingResponse(event_stream(redis, channel), media_type="text/event-stream")


async def publish_event(redis: Redis, player_id: int, payload: dict) -> None:
    """Publish event to player's SSE channel."""
    channel = f"sse:{player_id}"
    await redis.publish(channel, json_dumps(payload))


def json_dumps(payload: dict) -> str:
    """Serialize payload to JSON string."""
    import json

    return json.dumps(payload, ensure_ascii=False)

