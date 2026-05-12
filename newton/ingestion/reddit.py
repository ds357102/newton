"""Reddit ingestion via PRAW. TODO: wire credentials + score by upvote velocity."""
from typing import AsyncIterator
from .base import IngestionWorker
from ..events import Event


class RedditWorker(IngestionWorker):
    name = "reddit"
    cadence_seconds = 600

    async def fetch(self, query: dict) -> AsyncIterator[Event]:
        # TODO: praw.Reddit(...).subreddit(query["subreddit"]).search(query["q"])
        return
        yield  # pragma: no cover
