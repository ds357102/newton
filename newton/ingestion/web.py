"""Open-web ingestion — sitemap polling for expo / trade-show pages, etc."""
from typing import AsyncIterator
from .base import IngestionWorker
from ..events import Event


class WebWorker(IngestionWorker):
    name = "web"
    cadence_seconds = 3600

    async def fetch(self, query: dict) -> AsyncIterator[Event]:
        # TODO: httpx GET sitemap.xml, diff against last seen, yield new urls
        return
        yield  # pragma: no cover
