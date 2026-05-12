"""X (Twitter) ingestion via v2 search. TODO: bearer auth + lists endpoint."""
from typing import AsyncIterator
from .base import IngestionWorker
from ..events import Event


class XWorker(IngestionWorker):
    name = "x"
    cadence_seconds = 600

    async def fetch(self, query: dict) -> AsyncIterator[Event]:
        # TODO: httpx GET https://api.twitter.com/2/tweets/search/recent
        return
        yield  # pragma: no cover
