"""LinkedIn ingestion. Use the official API + RSS proxies that respect TOS."""
from typing import AsyncIterator
from .base import IngestionWorker
from ..events import Event


class LinkedInWorker(IngestionWorker):
    name = "linkedin"
    cadence_seconds = 1800

    async def fetch(self, query: dict) -> AsyncIterator[Event]:
        # TODO: LinkedIn company page API + named-person activity via approved channels
        return
        yield  # pragma: no cover
