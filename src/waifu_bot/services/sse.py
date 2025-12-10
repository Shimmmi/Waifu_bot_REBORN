from datetime import datetime
from typing import AsyncIterator

from fastapi import Request
from fastapi.responses import StreamingResponse


def event_stream(_: Request) -> AsyncIterator[str]:
    # Placeholder SSE stream. Replace with per-user channels when gameplay events are wired.
    yield f"data: {datetime.utcnow().isoformat()}\\n\\n"


def sse_response(request: Request) -> StreamingResponse:
    return StreamingResponse(event_stream(request), media_type="text/event-stream")

