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
    # 비용 상한 겸 응답 길이 제한 — 길이 제어 자체는 시스템 프롬프트의 적응형
    # 응답 원칙이 담당하므로 1024로 충분 (간결한 답변은 여기 한참 못 미침)
    model_settings=ModelSettings(max_tokens=1024),
)

for _tool in MES_TOOLS:
    mes_agent.tool(_tool)
