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
    # 한국어+마크다운 표는 토큰 소모가 커서 1024로는 중간에 잘림 — 2048로 상향.
    # 답변 길이는 토큰 상한이 아니라 시스템 프롬프트의 적응형 응답 원칙으로 제어한다.
    model_settings=ModelSettings(max_tokens=2048),
)

for _tool in MES_TOOLS:
    mes_agent.tool(_tool)
