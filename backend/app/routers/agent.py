"""LLM MES Agent endpoint — SSE streaming, adapted from QUARK chat.py."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.deps import MesDeps
from app.agents.mes_agent import mes_agent
from app.agents.routing import build_model
from app.core.database import get_db_optional
from app.core.redis import get_redis
from app.services.memory import (
    redis_append_conversation,
    redis_get_conversation,
    to_message_history,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["agent"])

# ── 비용/루프 안전장치 ────────────────────────────────────────────────────────
_MAX_MESSAGE_CHARS = 500    # 입력 메시지 최대 길이
_MAX_HISTORY_TURNS = 6      # 전송할 최대 대화 턴 수 (user+assistant 쌍)
_AGENT_TIMEOUT_SECS = 30    # 응답 전체 타임아웃
_RATE_LIMIT_WINDOW = 60     # rate limit 윈도우(초)
_RATE_LIMIT_MAX = 10        # 세션당 윈도우 내 최대 요청 수


class ChatRequest(BaseModel):
    message: str
    session_id: str = ""

    @field_validator("message")
    @classmethod
    def check_length(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("메시지가 비어 있습니다")
        if len(v) > _MAX_MESSAGE_CHARS:
            raise ValueError(
                f"메시지는 {_MAX_MESSAGE_CHARS}자 이하로 입력해주세요 (현재: {len(v)}자)"
            )
        return v


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _check_rate_limit(redis: aioredis.Redis, key_suffix: str) -> None:
    """분당 요청 수 제한 — Redis INCR + EXPIRE. session_id와 IP 둘 다에 적용."""
    key = f"mes:ratelimit:{key_suffix}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, _RATE_LIMIT_WINDOW)
    if count > _RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=429,
            detail=f"요청이 너무 많습니다. {_RATE_LIMIT_WINDOW}초 후 다시 시도하세요.",
        )


async def _stream_agent(
    req: Request,
    message: str,
    session_id: str,
    redis: aioredis.Redis,
    db: AsyncSession | None,
) -> AsyncGenerator[str, None]:
    try:
        turns = await redis_get_conversation(redis, session_id)
        # 최근 N턴만 전송 — 오래된 컨텍스트로 인한 토큰 낭비 방지
        history = list(to_message_history(turns))[-_MAX_HISTORY_TURNS * 2:]

        simulator = getattr(req.app.state, "simulator", None)
        deps = MesDeps(redis=redis, db=db, simulator=simulator)
        full_response = ""

        try:
            # asyncio.timeout: 30초 초과 시 TimeoutError → 무한 tool call 루프 강제 종료
            async with asyncio.timeout(_AGENT_TIMEOUT_SECS):
                async with mes_agent.run_stream(
                    message,
                    model=build_model(message),  # 메시지 복잡도에 따라 nano/mini 라우팅
                    deps=deps,
                    message_history=history,
                ) as result:
                    async for delta in result.stream_text(delta=True):
                        full_response += delta
                        yield _sse({"delta": delta, "done": False})

        except asyncio.TimeoutError:
            full_response += f"\n\n[응답 시간 초과 ({_AGENT_TIMEOUT_SECS}초) — 중단됨]"
            yield _sse({"delta": f"\n\n[응답 시간 초과 ({_AGENT_TIMEOUT_SECS}초)]", "done": True})
            await redis_append_conversation(redis, session_id, "user", message)
            await redis_append_conversation(redis, session_id, "assistant", full_response)
            return

        yield _sse({"delta": "", "done": True})

        await redis_append_conversation(redis, session_id, "user", message)
        await redis_append_conversation(redis, session_id, "assistant", full_response)

    except HTTPException:
        raise
    except Exception:
        logger.exception("Agent stream error")
        yield _sse({"delta": "\n\n[에이전트 오류 발생]", "done": True})


@router.post("/chat/stream")
async def chat_stream(
    req: Request,
    body: ChatRequest,
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
    db: Annotated[AsyncSession | None, Depends(get_db_optional)],
) -> StreamingResponse:
    session_id = body.session_id or str(uuid.uuid4())
    client_ip = req.client.host if req.client else "unknown"
    await _check_rate_limit(redis, f"ip:{client_ip}")
    await _check_rate_limit(redis, f"session:{session_id}")
    return StreamingResponse(
        _stream_agent(req, body.message, session_id, redis, db),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
            "X-Session-Id": session_id,
        },
    )


@router.delete("/chat/{session_id}")
async def clear_session(
    session_id: str,
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
) -> dict:
    await redis.delete(f"mes:conv:{session_id}")
    return {"cleared": session_id}
