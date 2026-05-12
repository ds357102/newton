"""RSS ingestion — works today; the simplest source to get a real feed flowing."""
from typing import AsyncIterator
from datetime import datetime
from uuid import uuid4

import feedparser

from .base import IngestionWorker
from ..events import Event


class RSSWorker(IngestionWorker):
    name = "rss"
    cadence_seconds = 1800

    async def fetch(self, query: dict) -> AsyncIterator[Event]:
        url = query["url"]
        parsed = feedparser.parse(url)
        for entry in parsed.entries[:20]:
            yield Event(
                id=uuid4(),
                source="rss",
                source_id=getattr(entry, "id", entry.link),
                ts_seen=datetime.utcnow(),
                ts_published=datetime(*entry.published_parsed[:6]) if hasattr(entry, "published_parsed") else None,
                payload={
                    "title": entry.title,
                    "url": entry.link,
                    "excerpt": getattr(entry, "summary", "")[:400],
                    "author": getattr(entry, "author", None),
                },
            )
