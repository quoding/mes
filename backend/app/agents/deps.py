from __future__ import annotations

from dataclasses import dataclass, field

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class MesDeps:
    """Runtime dependencies injected into the MES agent via RunContext."""

    redis: aioredis.Redis | None = None
    db: AsyncSession | None = None
    # Simulator reference for inject_test_anomaly tool
    simulator: object | None = field(default=None, repr=False)
