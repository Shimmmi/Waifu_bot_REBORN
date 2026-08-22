from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from waifu_bot.services.llm_usage import bind_llm_http, reset_llm_context


class LlmUsageHttpMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        tokens = bind_llm_http(request.method, request.url.path)
        try:
            return await call_next(request)
        finally:
            reset_llm_context(tokens)
