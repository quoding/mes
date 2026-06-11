"""Redis 기반 고정 윈도우 rate limiter — LLM 호출 엔드포인트의 비용 남용 방지."""
from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import HTTPException


async def check_rate_limit(
    redis: aioredis.Redis,
    key_suffix: str,
    max_calls: int,
    window_seconds: int = 60,
) -> None:
    """윈도우 내 호출 수가 max_calls를 넘으면 429. INCR + 첫 호출 시 EXPIRE."""
    key = f"mes:ratelimit:{key_suffix}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window_seconds)
    if count > max_calls:
        raise HTTPException(
            status_code=429,
            detail=f"요청이 너무 많습니다. {window_seconds}초 후 다시 시도하세요.",
        )
