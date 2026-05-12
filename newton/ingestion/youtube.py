"""YouTube ingestion via Data API v3.

v0.2 stub. v0.3 wires the real client + caption fetch so the LLM scorer can read
transcripts (especially useful for investor-day Q&A and trade-show keynotes).
"""
from __future__ import annotations
from typing import AsyncIterator

from .base import IngestionWorker
from ..events import Event


class YouTubeWorker(IngestionWorker):
    name = "youtube"
    cadence_seconds = 1800

    async def fetch(self, query: dict) -> AsyncIterator[Event]:
        # TODO: googleapiclient youtube v3 — search + channels + captions
        return
        yield  # pragma: no cover
