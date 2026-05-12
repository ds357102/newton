"""KPI ticker — REST snapshot + WebSocket fan-out."""
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..ticker.service import ticker_service

router = APIRouter()


@router.get("")
async def snapshot():
    """Current KPI snapshot, all symbols."""
    return await ticker_service.snapshot()


@router.websocket("/ws")
async def stream(ws: WebSocket):
    """Push live deltas as KPIs change."""
    await ws.accept()
    queue: asyncio.Queue = asyncio.Queue()
    ticker_service.subscribe(queue)
    try:
        while True:
            msg = await queue.get()
            await ws.send_json(msg)
    except WebSocketDisconnect:
        pass
    finally:
        ticker_service.unsubscribe(queue)
