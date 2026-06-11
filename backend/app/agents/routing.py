"""Model routing: select nano (fast) vs mini (complex) based on message heuristics."""
from __future__ import annotations

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.core.config import get_settings

settings = get_settings()

_COMPLEX_MARKERS: tuple[str, ...] = (
    "분석",
    "비교",
    "요약",
    "원인",
    "보고서",
    "예측",
    "상관",
    "이상",
    "explain",
    "analyze",
    "report",
    "predict",
)

_COMPLEX_THRESHOLD_CHARS = 150
_COMPLEX_MARKER_HITS = 2


def select_model_id(message: str) -> str:
    if len(message) > _COMPLEX_THRESHOLD_CHARS:
        return settings.openai_model_complex
    hits = sum(1 for m in _COMPLEX_MARKERS if m in message)
    if hits >= _COMPLEX_MARKER_HITS:
        return settings.openai_model_complex
    return settings.openai_model_default


def build_model(message: str) -> OpenAIChatModel:
    model_id = select_model_id(message)
    provider = OpenAIProvider(api_key=settings.openai_api_key or "sk-no-key-configured")
    return OpenAIChatModel(model_id, provider=provider)
