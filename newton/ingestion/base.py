"""Ingestion worker base — one subclass per source family."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import AsyncIterator

from ..events import Event


class IngestionWorker(ABC):
    name: str = "base"
    cadence_seconds: int = 900

    @abstractmethod
    async def fetch(self, query: dict) -> AsyncIterator[Event]:
        """Yield Events for a single query against this source."""
        if False:
            yield  # pragma: no cover
