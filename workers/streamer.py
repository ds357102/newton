"""Continuous ingestion streamer.

Runs forever. Every NEWTON_STREAM_INTERVAL_SEC seconds:
  1. PER-PROSPECT FETCH — Google News RSS for each prospect's query bundle.
  2. INDUSTRY FETCH    — a curated list of free industry RSS feeds covering
                         manufacturing, CPG, food, energy, building materials,
                         packaging, auto, aero/defense, automation, expos.
  3. REDDIT FETCH      — relevant subreddit RSS feeds (no key required).
  4. ATTRIBUTION       — every fetched item is cross-referenced against all
                         prospect query bundles. Items that mention a prospect
                         (by name, DBA, or domain) are annotated for that
                         prospect and run through the full pipeline.
  5. DEDUP             — by URL hash within the cycle.
  6. PERSIST           — surviving hits write to disk so the UI picks them up.

All sources here are FREE (no API key required). X / LinkedIn / paid sources
are intentionally not included.

Env knobs:
  NEWTON_STREAM_INTERVAL_SEC   default 900 (15 min)
  NEWTON_HITS_FILE             default newton/data/seed_hits.json
  NEWTON_MAX_HITS_PER_PROSPECT default 10
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import signal
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

import feedparser
import httpx

from newton.events import Event
from newton.prospects.source import prospect_source, Prospect
from newton.prospects.monitor import annotate_with_llm
from newton.store import hits as hits_store


INTERVAL = int(os.environ.get("NEWTON_STREAM_INTERVAL_SEC", "900"))
HITS_FILE = Path(os.environ.get("NEWTON_HITS_FILE") or
                 Path(__file__).resolve().parent.parent / "newton" / "data" / "seed_hits.json")
MAX_HITS_PER_PROSPECT = int(os.environ.get("NEWTON_MAX_HITS_PER_PROSPECT", "10"))
HTTP_TIMEOUT = 20

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


# ---------------------------------------------------------------------------
# FREE INDUSTRY RSS FEEDS — manufacturing + companies that ship things
# ---------------------------------------------------------------------------
# Curated. All publicly available. No key required. Add or trim as you learn
# which ones produce signal vs. noise.
INDUSTRY_FEEDS: list[tuple[str, str]] = [
    # --- Freight / supply chain (anchor industry) ---
    ("FreightWaves",            "https://www.freightwaves.com/feed"),
    ("Supply Chain Dive",       "https://www.supplychaindive.com/feeds/news/"),
    ("Logistics Mgmt",          "https://www.logisticsmgmt.com/rss"),
    ("Modern Materials Hndlg",  "https://www.mmh.com/rss"),
    ("Material Handling & Log", "https://www.mhlnews.com/rss.xml"),
    ("Transport Topics",        "https://www.ttnews.com/rss.xml"),

    # --- Manufacturing & industrial ---
    ("IndustryWeek",            "https://www.industryweek.com/rss.xml"),
    ("The Manufacturer (UK)",   "https://www.themanufacturer.com/feed/"),
    ("Manufacturing.net",       "https://www.manufacturing.net/rss.xml"),
    ("Modern Machine Shop",     "https://www.mmsonline.com/rss/articles"),
    ("Plant Engineering",       "https://www.plantengineering.com/feed/"),
    ("Assembly Magazine",       "https://www.assemblymag.com/rss/articles"),

    # --- Automation & robotics ---
    ("Automation World",        "https://www.automationworld.com/rss.xml"),
    ("Control Engineering",     "https://www.controleng.com/feed/"),
    ("Robotics Business Review","https://www.roboticsbusinessreview.com/feed/"),

    # --- CPG / food / beverage ---
    ("Food Dive",               "https://www.fooddive.com/feeds/news/"),
    ("Food Processing",         "https://www.foodprocessing.com/rss/"),
    ("Beverage Industry",       "https://www.bevindustry.com/rss/topic/8055-bi-online-news"),
    ("Food Navigator USA",      "https://www.foodnavigator-usa.com/Info/RSS"),
    ("Bakery & Snacks",         "https://www.bakeryandsnacks.com/Info/RSS"),

    # --- Packaging ---
    ("Packaging Dive",          "https://www.packagingdive.com/feeds/news/"),
    ("Packaging Digest",        "https://www.packagingdigest.com/rss.xml"),
    ("Plastics News",           "https://www.plasticsnews.com/news.xml"),

    # --- Building materials & construction ---
    ("Construction Dive",       "https://www.constructiondive.com/feeds/news/"),
    ("Building Design+Constr",  "https://www.bdcnetwork.com/rss.xml"),
    ("ENR",                     "https://www.enr.com/rss/articles"),

    # --- Energy ---
    ("OilPrice.com",            "https://oilprice.com/rss/main"),
    ("Energy News Network",     "https://energynews.us/feed/"),
    ("Power Magazine",          "https://www.powermag.com/feed/"),

    # --- Auto / aero / defense ---
    ("Automotive News",         "https://www.autonews.com/rss"),
    ("Defense News",            "https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml"),
    ("Aviation Week",           "https://aviationweek.com/feed"),

    # --- Press wires (cross-industry announcements) ---
    ("PRNewswire — Mfg",        "https://www.prnewswire.com/rss/business-technology-news/manufacturing-news.rss"),
    ("PRNewswire — CPG",        "https://www.prnewswire.com/rss/consumer-services/consumer-goods-retail-news.rss"),
    ("BusinessWire — Mfg",      "https://www.businesswire.com/portal/site/home/template.RSS/index.gsp?categoryId=31407"),

    # --- Trade shows / expos ---
    ("Trade Show News Network", "https://www.tsnn.com/feed"),
    ("Exhibit City News",       "https://www.exhibitcitynews.com/feed/"),
]


# ---------------------------------------------------------------------------
# REDDIT SUBREDDIT RSS — free, no key required
# ---------------------------------------------------------------------------
REDDIT_SUBREDDITS: list[str] = [
    "Logistics", "SupplyChain", "freight", "Trucking",
    "manufacturing", "industrialdesign",
    "automation", "robotics",
    "CPG", "FoodIndustry", "foodscience",
    "AutoIndustry", "cars",
    "aerospace", "aviation",
    "energy", "renewableenergy",
    "Construction", "ConstructionTech",
    "packaging",
]


def _reddit_rss(subreddit: str) -> tuple[str, str]:
    return (f"r/{subreddit}", f"https://www.reddit.com/r/{subreddit}/.rss")


REDDIT_FEEDS: list[tuple[str, str]] = [_reddit_rss(s) for s in REDDIT_SUBREDDITS]


# ---------------------------------------------------------------------------
log = logging.getLogger("newton.streamer")
_running = True


def _on_signal(*a):
    global _running
    log.info("shutdown signal received; finishing current cycle")
    _running = False


# ---------------------------------------------------------------------------
# Fetchers
# ---------------------------------------------------------------------------
def _fetch_rss(url: str, source_name: str, *, limit: int = 25) -> list[dict]:
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=True,
                          headers={"User-Agent": "newton/0.6 (+web)"}) as client:
            r = client.get(url)
            r.raise_for_status()
            parsed = feedparser.parse(r.text)
    except Exception as e:
        log.warning(f"[{source_name}] fetch failed: {e}")
        return []
    items = []
    for entry in parsed.entries[:limit]:
        ts_pub = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            ts_pub = datetime(*entry.published_parsed[:6])
        items.append({
            "title": entry.get("title", "") or "",
            "url": entry.get("link", "") or "",
            "excerpt": (entry.get("summary", "") or "")[:500],
            "ts_published": ts_pub,
            "source_id": entry.get("id", entry.get("link")),
            "source_name": source_name,
        })
    return items


def fetch_google_news_for_query(query: str) -> list[dict]:
    return _fetch_rss(GOOGLE_NEWS_RSS.format(q=quote_plus(query)),
                      source_name="google-news")


def fetch_industry_feed(name: str, url: str) -> list[dict]:
    return _fetch_rss(url, source_name=name)


def fetch_reddit_feed(name: str, url: str) -> list[dict]:
    return _fetch_rss(url, source_name=name, limit=20)


# ---------------------------------------------------------------------------
# Attribution: which prospect (if any) does this item mention?
# ---------------------------------------------------------------------------
def attribute_to_prospects(item: dict, prospects: list[Prospect]) -> list[Prospect]:
    """Return prospects whose name / aliases / domains appear in the item text.
    Many industry articles mention multiple companies — attribute to each.

    Uses word-boundary matching for short terms (< 8 chars) to avoid false
    positives like 'Price' matching inside 'prices' or 'Seco' in 'second'.
    Longer terms use substring matching since they're unlikely to collide.
    """
    import re
    text = f"{item.get('title','')} {item.get('excerpt','')}".lower()
    matches = []
    for p in prospects:
        terms = [p.name, *p.dba_aliases, *p.domains]
        for t in terms:
            t_low = (t or "").lower().strip()
            if not t_low or len(t_low) < 4:
                continue
            # For short terms, require word boundaries to avoid substring false positives
            if len(t_low) < 8:
                pattern = r'\b' + re.escape(t_low) + r'\b'
                if re.search(pattern, text):
                    matches.append(p)
                    break
            else:
                if t_low in text:
                    matches.append(p)
                    break
    return matches


def _hit_dict(h, source_name: str) -> dict:
    age = ""
    if h.event.ts_published:
        age_d = (datetime.utcnow() - h.event.ts_published).days
        age_h = (datetime.utcnow() - h.event.ts_published).total_seconds() / 3600
        age = f"{int(age_h)}h" if age_d < 1 else f"{age_d}d"
    return {
        "signal_category": h.signal_category,
        "freshness_status": h.freshness.status,
        "title": h.event.payload.get("title"),
        "excerpt": h.event.payload.get("excerpt"),
        "url": h.event.payload.get("url"),
        "score": round(h.event.score, 3),
        "reason": (h.event.score_reason or "")[:200],
        "source": source_name,
        "age": age,
        "matched_cues": h.matched_cues,
    }


# ---------------------------------------------------------------------------
# Cycle
# ---------------------------------------------------------------------------
async def cycle() -> dict[str, list[dict]]:
    """One pass over every source × every prospect."""
    prospects = await prospect_source.all()
    log.info(f"cycle starting: {len(prospects)} prospects, "
             f"{len(INDUSTRY_FEEDS)} industry feeds, {len(REDDIT_FEEDS)} reddit feeds")

    new_hits: dict[str, list[dict]] = {p.id: [] for p in prospects}
    seen_urls: set[str] = set()

    async def process_item(item: dict, attributed: list[Prospect]):
        url = item.get("url")
        if not url or url in seen_urls:
            return
        seen_urls.add(url)
        for p in attributed:
            ev = Event(
                source="rss",
                source_id=item.get("source_id") or url,
                ts_published=item.get("ts_published"),
                payload={
                    "title": item.get("title"),
                    "url": url,
                    "excerpt": item.get("excerpt"),
                },
            )
            hit = await annotate_with_llm(ev, p)
            if hit.freshness.status == "suppressed":
                continue
            new_hits[p.id].append(_hit_dict(hit, item.get("source_name", "rss")))

    # 1) Per-prospect Google News fetches — PRIORITY PROSPECTS ONLY
    #    With 3,695 prospects × 3 queries each, scanning all would take hours.
    #    Priority prospects get dedicated Google News searches.
    #    Non-priority prospects still get coverage via industry/Reddit attribution.
    priority_prospects = [p for p in prospects if p.priority]
    log.info(f"  google-news: scanning {len(priority_prospects)} priority prospects "
             f"(skipping {len(prospects) - len(priority_prospects)} non-priority)")
    for p in priority_prospects:
        for q in p.query_bundle()[:3]:
            for it in fetch_google_news_for_query(q):
                await process_item(it, [p])

    # 2) Industry feeds — cross-reference against ALL prospects
    industry_items = industry_matches = 0
    for name, url in INDUSTRY_FEEDS:
        items = fetch_industry_feed(name, url)
        industry_items += len(items)
        for it in items:
            attributed = attribute_to_prospects(it, prospects)
            if attributed:
                industry_matches += 1
                await process_item(it, attributed)
    log.info(f"  industry: fetched {industry_items}; {industry_matches} attributed")

    # 3) Reddit feeds — cross-reference against ALL prospects
    reddit_items = reddit_matches = 0
    for name, url in REDDIT_FEEDS:
        items = fetch_reddit_feed(name, url)
        reddit_items += len(items)
        for it in items:
            attributed = attribute_to_prospects(it, prospects)
            if attributed:
                reddit_matches += 1
                await process_item(it, attributed)
    log.info(f"  reddit: fetched {reddit_items}; {reddit_matches} attributed")

    # Sort + cap per prospect
    for pid, hit_list in new_hits.items():
        hit_list.sort(key=lambda h: h["score"], reverse=True)
        new_hits[pid] = hit_list[:MAX_HITS_PER_PROSPECT]

    total = sum(len(v) for v in new_hits.values())
    log.info(f"cycle done: {total} hits surfaced (from {len(seen_urls)} unique URLs)")
    return new_hits


def persist(hits: dict) -> None:
    HITS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = HITS_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(hits, f, indent=2, default=str)
    tmp.replace(HITS_FILE)


async def main() -> None:
    logging.basicConfig(
        level=os.environ.get("NEWTON_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    log.info(f"streamer up. interval={INTERVAL}s; hits_file={HITS_FILE}")
    log.info(f"sources: google-news (per-prospect) + {len(INDUSTRY_FEEDS)} industry + {len(REDDIT_FEEDS)} reddit feeds")
    while _running:
        try:
            new_hits = await cycle()
            hits_store.replace_all(new_hits)
            persist(new_hits)
        except Exception as e:
            log.exception(f"cycle failed: {e}")
        for _ in range(INTERVAL):
            if not _running:
                break
            await asyncio.sleep(1)
    log.info("streamer stopped cleanly")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
