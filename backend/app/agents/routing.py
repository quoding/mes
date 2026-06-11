"""Model selection — 비용 절감을 위해 nano 단일 모델만 사용한다.

복잡도 기반 nano/mini 라우팅이 있었으나 포트폴리오 데모에서는 API 요금
최소화가 우선이라 제거. 운영 전환 시 select_model_id 휴리스틱을 복원하면 됨
(git history 참고).
"""
from __future__ import annotations

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.core.config import get_settings

settings = get_settings()


def select_model_id(message: str) -> str:  # noqa: ARG001 — 시그니처 호환 유지
    return settings.openai_model_default


def build_model(message: str) -> OpenAIChatModel:
    provider = OpenAIProvider(api_key=settings.openai_api_key or "sk-no-key-configured")
    return OpenAIChatModel(select_model_id(message), provider=provider)
