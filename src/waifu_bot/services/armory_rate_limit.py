"""Redis-backed rate limiting for Armory API."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request, status


async def check_rate_limit(
    redis: Any,
    *,
    key: str,
    limit: int,
    window_sec: int = 60,
) -> None:
    if not redis:
        return
    bucket = f"armory:rl:{key}"
    count = await redis.incr(bucket)
    if count == 1:
        await redis.expire(bucket, window_sec)
    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="rate_limit_exceeded",
        )


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


async def rate_limit_by_ip(redis: Any, request: Request, endpoint: str, limit: int) -> None:
    ip = client_ip(request)
    await check_rate_limit(redis, key=f"ip:{endpoint}:{ip}", limit=limit)


async def rate_limit_by_user(redis: Any, tg_id: int, endpoint: str, limit: int) -> None:
    await check_rate_limit(redis, key=f"user:{endpoint}:{tg_id}", limit=limit)
