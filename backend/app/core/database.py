from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=settings.environment == "development",
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db_optional() -> AsyncGenerator[AsyncSession | None, None]:
    try:
        session = AsyncSessionLocal()
    except Exception:
        yield None
        return

    async with session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    import logging
    import app.models  # noqa: F401

    _log = logging.getLogger(__name__)

    async with engine.begin() as conn:
        # Enable TimescaleDB — gracefully degrade to plain Postgres if unavailable
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE"))
            _timescale = True
        except Exception:
            _log.warning("TimescaleDB extension not available — running as plain PostgreSQL")
            _timescale = False

        await conn.run_sync(Base.metadata.create_all)

        if _timescale:
            try:
                await conn.execute(text("""
                    SELECT create_hypertable(
                        'process_data', 'time',
                        if_not_exists => TRUE,
                        migrate_data => TRUE
                    )
                """))
            except Exception:
                _log.warning("create_hypertable failed — process_data will use standard table")

            try:
                await conn.execute(text("""
                    SELECT add_retention_policy('process_data', INTERVAL '7 days', if_not_exists => TRUE)
                """))
            except Exception:
                _log.warning("add_retention_policy failed — process_data will grow unbounded")
