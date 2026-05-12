"""Background worker entrypoint.

For v0.1: poll the registered RSS sources every cadence, push events to the API.
v0.2 swaps polling for an RQ/BullMQ scheduler with per-source queues.
"""
import asyncio
import logging
from datetime import datetime

from newton.ingestion.rss import RSSWorker
from newton.scoring.rules import score_rules


SEED_RSS = [
    {"url": "https://www.freightwaves.com/feed"},
    # add more once .env is configured
]


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("newton.worker")
    rss = RSSWorker()

    while True:
        for q in SEED_RSS:
            try:
                async for ev in rss.fetch(q):
                    score, reason = score_rules(ev, watchlist_terms=["freight", "logistics"])
                    ev.score = score
                    ev.score_reason = reason
                    # TODO: persist via SessionLocal()
                    log.info("event %.2f %s", ev.score, ev.payload.get("title"))
            except Exception as e:
                log.exception("rss fetch failed: %s", e)
        await asyncio.sleep(rss.cadence_seconds)


if __name__ == "__main__":
    asyncio.run(main())
