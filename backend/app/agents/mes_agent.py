"""PNT MES LLM Agent — Pydantic AI based, QUARK agent pattern adapted."""
from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from app.agents.deps import MesDeps
from app.agents.prompts import MES_SYSTEM_PROMPT
from app.agents.tools import MES_TOOLS

mes_agent: Agent[MesDeps, str] = Agent(
    model="openai:gpt-5.4-nano",
    deps_type=MesDeps,
    system_prompt=MES_SYSTEM_PROMPT,
    retries=1,           # 툴 인자 검증 실패 시 1회 재시도 — 루프 방지는 30초 타임아웃이 담당
    model_settings=ModelSettings(max_tokens=1024),  # 응답 토큰 상한
)

for _tool in MES_TOOLS:
    mes_agent.tool(_tool)
