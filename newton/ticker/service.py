"""KPI ticker — keeps current values, broadcasts deltas to subscribers."""
from __future__ import annotations
import asyncio
from typing import Any

from .adapters.base import KPIAdapter
from .adapters.mock import MockKPIAdapter


class TickerService:
    def __init__(self, adapter: KPIAdapter | None = None) -> None:
        self.adapter = adapter or MockKPIAdapter()
        self._subs: set[asyncio.Queue] = set()
        self._values: dict[str, dict[str, Any]] = {}

    async def snapshot(self) -> dict[str, Any]:
        if not self._values:
            self._values = await self.adapter.fetch_all()
        return {"symbols": list(self._values.values())}

    def subscribe(self, q: asyncio.Queue) -> None:
        self._subs.add(q)

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    async def publish(self, delta: dict[str, Any]) -> None:
        sym = delta.get("sym")
        if sym:
            self._values[sym] = {**self._values.get(sym, {}), **delta}
        for q in list(self._subs):
            await q.put(delta)


ticker_service = TickerService()
