from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import init_db
from app.core.redis import close_pool
from app.routers import health

settings = get_settings()
logging.basicConfig(level=settings.log_level.upper())
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("PNT MES API starting — env=%s", settings.environment)

    await init_db()

    from app.services.simulator import ProcessSimulator
    from app.services.anomaly_engine import anomaly_engine

    simulator = ProcessSimulator()
    app.state.simulator = simulator

    # Keep task references so we can cancel them cleanly on shutdown
    sim_task = asyncio.create_task(simulator.run(), name="simulator")
    eng_task = asyncio.create_task(anomaly_engine.run(), name="anomaly-engine")

    yield

    logger.info("PNT MES API shutting down")
    simulator.stop()
    anomaly_engine.stop()

    # Cancel and await so shutdown doesn't hang
    for task in (sim_task, eng_task):
        task.cancel()
        try:
            await task
        except BaseException:
            pass

    await close_pool()


app = FastAPI(
    title="PNT MES Agent API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

_dev_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_dev_origins if settings.environment != "production" else ["https://pnt-mes.example.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Session-Id"],
)

app.include_router(health.router)

# Routers added incrementally per phase
# Phase 3+
from app.routers import ws as ws_router  # noqa: E402
from app.routers import process as process_router  # noqa: E402
from app.routers import anomaly as anomaly_router  # noqa: E402
from app.routers import correlation as correlation_router  # noqa: E402
from app.routers import maintenance as maintenance_router  # noqa: E402
from app.routers import agent as agent_router  # noqa: E402
from app.routers import alerts as alerts_router  # noqa: E402

app.include_router(ws_router.router)
app.include_router(process_router.router, prefix="/api")
app.include_router(anomaly_router.router, prefix="/api")
app.include_router(correlation_router.router, prefix="/api")
app.include_router(maintenance_router.router, prefix="/api")
app.include_router(agent_router.router, prefix="/api")
app.include_router(alerts_router.router, prefix="/api")
