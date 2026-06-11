from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _read_secret(name: str) -> str:
    path = Path(f"/run/secrets/{name}")
    if path.exists():
        return path.read_text().strip()
    return ""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    log_level: str = "info"

    # OpenAI — 비용 절감을 위해 nano 단일 모델 사용
    openai_model_default: str = "gpt-5.4-nano"

    # Postgres
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "pnt_mes"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_ttl_seconds: int = 86400

    # Simulator
    simulator_interval_ms: int = 500
    anomaly_inject_prob: float = 0.015

    @computed_field  # type: ignore[prop-decorator]
    @property
    def openai_api_key(self) -> str:
        return _read_secret("openai_api_key") or os.environ.get("OPENAI_API_KEY", "")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def postgres_user(self) -> str:
        return _read_secret("postgres_user") or os.environ.get("POSTGRES_USER", "pnt")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def postgres_password(self) -> str:
        return _read_secret("postgres_password") or os.environ.get("POSTGRES_PASSWORD", "pnt")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def redis_password(self) -> str:
        return _read_secret("redis_password") or ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        u, p = self.postgres_user, self.postgres_password
        h, port, db = self.postgres_host, self.postgres_port, self.postgres_db
        return f"postgresql+asyncpg://{u}:{p}@{h}:{port}/{db}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def redis_url(self) -> str:
        pw = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{pw}{self.redis_host}:{self.redis_port}/0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
