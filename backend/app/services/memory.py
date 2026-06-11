from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from app.core.config import get_settings

settings = get_settings()


async def redis_set(redis: aioredis.Redis, key: str, value: Any, ttl: int | None = None) -> None:
    await redis.set(key, json.dumps(value), ex=ttl or settings.redis_ttl_seconds)


async def redis_get(redis: aioredis.Redis, key: str) -> Any | None:
    raw = await redis.get(key)
    return json.loads(raw) if raw else None


async def redis_append_conversation(
    redis: aioredis.Redis, session_id: str, role: str, content: str
) -> None:
    key = f"mes:conv:{session_id}"
    await redis.rpush(key, json.dumps({"role": role, "content": content}))
    await redis.expire(key, settings.redis_ttl_seconds)


async def redis_get_conversation(redis: aioredis.Redis, session_id: str) -> list[dict]:
    key = f"mes:conv:{session_id}"
    entries = await redis.lrange(key, 0, -1)
    return [json.loads(e) for e in entries]


def to_message_history(turns: list[dict[str, str]]) -> list[ModelMessage]:
    history: list[ModelMessage] = []
    for turn in turns:
        content = turn.get("content", "")
        if turn.get("role") == "user":
            history.append(ModelRequest(parts=[UserPromptPart(content=content)]))
        else:
            history.append(ModelResponse(parts=[TextPart(content=content)]))
    return history
