"""WebSocket endpoint: broadcasts real-time process data from Redis pub/sub."""
from __future__ import annotations

import asyncio
import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.redis import get_pool

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


@router.websocket("/ws/live")
async def ws_live(websocket: WebSocket) -> None:
    """Stream real-time sensor readings to the client.

    Each message is a JSON array of ProcessReading objects published by the simulator.
    """
    await websocket.accept()
    pool = get_pool()
    # Store client explicitly — anonymous instance would be GC'd before pubsub finishes
    redis_client = aioredis.Redis(connection_pool=pool)
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("process:live")
    logger.info("WS client connected")

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    await websocket.send_text(message["data"])
                except WebSocketDisconnect:
                    break
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception:
        logger.exception("WS error")
    finally:
        try:
            await pubsub.unsubscribe("process:live")
            await pubsub.aclose()
        except Exception:
            pass
        logger.info("WS client disconnected")


@router.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket) -> None:
    """Stream Layer 4 failure-signature alerts (RAISED/ACTIVE/RESOLVED/UPDATED)."""
    await websocket.accept()
    pool = get_pool()
    redis_client = aioredis.Redis(connection_pool=pool)
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("alert:live")
    logger.info("WS alerts client connected")

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    await websocket.send_text(message["data"])
                except WebSocketDisconnect:
                    break
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception:
        logger.exception("WS alerts error")
    finally:
        try:
            await pubsub.unsubscribe("alert:live")
            await pubsub.aclose()
        except Exception:
            pass
        logger.info("WS alerts client disconnected")
