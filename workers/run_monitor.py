"""v0.4 — Local prospect-monitor runner.

Run on your machine (NOT in the sandbox; the sandbox proxy blocks news domains).
Fetches Google News RSS for each prospect you specify, runs the full Newton
pipeline (ingest → score → classify → freshness gate → archive dedupe), and
prints + saves the hits.

Usage:
  # default demo prospects (food + industrial manufacturers, freight-heavy):
  python -m workers.run_monitor

  # your own prospects:
  python -m workers.run_monitor --prospect "Tyson Foods" --prospect "General Mills"

  # offline mode — canned data, no network:
  python -m workers.run_monitor --demo

  # JSON output to a file:
  python -m workers.run_monitor --out hits.json
"""
from __future__ import annotations
import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from urllib.parse import quote_plus
from uuid import uuid4

import feedparser
import httpx

# Newton modules
from newton.config import settings
from newton.events import Event
from newton.prospects.source import Prospect
from newton.prospects.monitor import annotate, annotate_with_llm, ProspectHit


GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
DEFAULT_PROSPECTS = ["Tyson Foods", "General Mills", "Stanley Black & Decker"]
PER_QUERY_TIMEOUT = 15


# ---------- prospect bootstrap ----------
def make_prospect(name: str, *, priority: bool = True) -> Prospect:
    """Quick demo Prospect — owner is 'me', no archive, treats as warm account."""
    return Prospect(
        id=f"demo_{name.lower().replace(' ', '_').replace('&','and')}",
        owner_id="o_me",
        name=name,
        priority=priority,
        added_at=datetime.utcnow() - timedelta(days=60),  # not cold-start
        last_touch_at=None,
        industry="manufacturing",
    )


# ---------- fetcher ----------
def fetch_google_news(query: str) -> list[dict]:
    """Return a list of dicts shaped like {title, url, excerpt, ts_published, source_id}."""
    url = GOOGLE_NEWS_RSS.format(q=quote_plus(query))
    try:
        with httpx.Client(timeout=PER_QUERY_TIMEOUT, follow_redirects=True,
                          headers={"User-Agent": "newton/0.4 (+local)"}) as client:
            r = client.get(url)
            r.raise_for_status()
            parsed = feedparser.parse(r.text)
    except Exception as e:
        print(f"  ! fetch failed for {query!r}: {e}", file=sys.stderr)
        return []

    items = []
    for entry in parsed.entries[:15]:
        ts_pub = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            ts_pub = datetime(*entry.published_parsed[:6])
        items.append({
            "title": entry.get("title", ""),
            "url": entry.get("link", ""),
            "excerpt": entry.get("summary", "")[:500],
            "author": entry.get("source", {}).get("title") if isinstance(entry.get("source"), dict) else None,
            "ts_published": ts_pub,
            "source_id": entry.get("id", entry.get("link")),
        })
    return items


# ---------- canned payloads for --demo mode ----------
def canned_payloads(prospect: Prospect) -> list[dict]:
    """Realistic-ish news for offline testing. The pipeline runs identically."""
    now = datetime.utcnow()
    pool = {
        "tyson foods": [
            {"title": f"{prospect.name} announces new $200M poultry processing plant in Arkansas",
             "url": "https://example.com/tyson-new-plant",
             "excerpt": "Tyson confirmed plans for a new processing facility; first phase targets Q2 with hiring for ~500 roles.",
             "ts_published": now - timedelta(days=3)},
            {"title": f"{prospect.name} files RFP for 2026 refrigerated lane awards",
             "url": "https://example.com/tyson-rfp",
             "excerpt": "Internal procurement memo references a carrier-bid window opening next quarter.",
             "ts_published": now - timedelta(days=22)},
            {"title": f"{prospect.name} posts Q1 earnings; supply chain costs flagged",
             "url": "https://example.com/tyson-earnings",
             "excerpt": "Earnings call named inbound freight and cold-storage capacity as ongoing pain points.",
             "ts_published": now - timedelta(days=8)},
            {"title": f"Old story from 2024 about {prospect.name}",
             "url": "https://example.com/tyson-old",
             "excerpt": "Should be suppressed by the freshness gate.",
             "ts_published": now - timedelta(days=540)},
        ],
        "general mills": [
            {"title": f"{prospect.name} acquires regional bakery in $150M deal",
             "url": "https://example.com/gm-acq",
             "excerpt": "Acquisition expands ambient-shelf product mix and adds a midwestern DC.",
             "ts_published": now - timedelta(days=5)},
            {"title": f"{prospect.name} launches new line of frozen breakfast products",
             "url": "https://example.com/gm-launch",
             "excerpt": "Product launch will require new frozen distribution lanes from Q3.",
             "ts_published": now - timedelta(days=11)},
        ],
        "stanley black & decker": [
            {"title": f"{prospect.name} opens new distribution center in Texas",
             "url": "https://example.com/swk-dc",
             "excerpt": "New DC consolidates outbound fulfillment for southwest region.",
             "ts_published": now - timedelta(days=4)},
            {"title": f"{prospect.name} announces $500M capex through 2027",
             "url": "https://example.com/swk-capex",
             "excerpt": "Capital plan covers fleet additions and warehouse automation.",
             "ts_published": now - timedelta(days=18)},
        ],
    }
    return pool.get(prospect.name.lower(), [])


# ---------- pipeline ----------
def event_from_payload(payload: dict) -> Event:
    return Event(
        source="rss",
        source_id=payload.get("source_id") or payload.get("url"),
        ts_seen=datetime.utcnow(),
        ts_published=payload.get("ts_published"),
        payload={
            "title": payload.get("title"),
            "url": payload.get("url"),
            "excerpt": payload.get("excerpt"),
            "author": payload.get("author"),
        },
    )


async def run(prospects: list[Prospect], *, demo: bool, use_llm: bool = True) -> dict:
    summary = {
        "ran_at": datetime.utcnow().isoformat() + "Z",
        "mode": "demo" if demo else "live",
        "llm": bool(use_llm and settings.anthropic_api_key),
        "prospects": [],
    }
    if use_llm and not settings.anthropic_api_key:
        print("  (ANTHROPIC_API_KEY not set — LLM pass will no-op; rules-only scoring)")

    for prospect in prospects:
        print(f"\n=== {prospect.name} ({prospect.id}) ===")
        if demo:
            payloads = canned_payloads(prospect)
            print(f"  using {len(payloads)} canned payload(s)")
        else:
            # Use the prospect's query bundle: name + aliases + cities + execs
            queries = prospect.query_bundle()
            print(f"  expanding to {len(queries)} quer{'y' if len(queries)==1 else 'ies'}: {queries[:3]}{'...' if len(queries)>3 else ''}")
            seen_urls = set()
            payloads = []
            for q in queries:
                for item in fetch_google_news(q):
                    if item["url"] in seen_urls:
                        continue
                    seen_urls.add(item["url"])
                    payloads.append(item)
            print(f"  fetched {len(payloads)} unique item(s)")

        hits: list[ProspectHit] = []
        suppressed = 0
        for payload in payloads:
            ev = event_from_payload(payload)
            hit = await annotate_with_llm(ev, prospect) if use_llm else annotate(ev, prospect)
            if hit.freshness.status == "suppressed":
                suppressed += 1
                continue
            hits.append(hit)

        # Sort: highest score first
        hits.sort(key=lambda h: h.event.score, reverse=True)

        print(f"  → {len(hits)} hits surfaced, {suppressed} suppressed by freshness gate")
        for h in hits[:8]:
            sig = h.signal_category
            fresh = h.freshness.status
            score = h.event.score
            age = ""
            if h.event.ts_published:
                age_d = (datetime.utcnow() - h.event.ts_published).days
                age = f"{age_d}d"
            print(f"    [{score:0.2f}] {sig:13s} {fresh:18s} {age:>5s}  {h.event.payload['title'][:90]}")

        summary["prospects"].append({
            "id": prospect.id,
            "name": prospect.name,
            "priority": prospect.priority,
            "hits_surfaced": len(hits),
            "suppressed": suppressed,
            "hits": [
                {
                    "title": h.event.payload.get("title"),
                    "url": h.event.payload.get("url"),
                    "excerpt": h.event.payload.get("excerpt"),
                    "signal_category": h.signal_category,
                    "freshness_status": h.freshness.status,
                    "freshness_reason": h.freshness.reason,
                    "score": round(h.event.score, 3),
                    "score_reason": h.event.score_reason,
                    "matched_cues": h.matched_cues,
                    "age_days": (datetime.utcnow() - h.event.ts_published).days if h.event.ts_published else None,
                    "ts_published": h.event.ts_published.isoformat() if h.event.ts_published else None,
                } for h in hits
            ],
        })

    return summary


# ---------- CLI ----------
def main() -> int:
    ap = argparse.ArgumentParser(description="Newton v0.4 prospect monitor — local runner")
    ap.add_argument("--prospect", action="append", help="prospect name (repeatable). Defaults to demo set.")
    ap.add_argument("--demo", action="store_true",
                    help="use canned payloads instead of fetching live (offline testing).")
    ap.add_argument("--no-llm", action="store_true",
                    help="skip the LLM classifier pass even if ANTHROPIC_API_KEY is set.")
    ap.add_argument("--out", default="newton_run.json",
                    help="path to save full JSON report (default: newton_run.json)")
    args = ap.parse_args()

    names = args.prospect or DEFAULT_PROSPECTS
    prospects = [make_prospect(n, priority=True) for n in names]
    use_llm = not args.no_llm

    print(f"Newton v0.5 — monitoring {len(prospects)} prospect(s) "
          f"({'demo / offline' if args.demo else 'live fetch via Google News RSS'}, "
          f"{'LLM on' if use_llm and settings.anthropic_api_key else 'LLM off'})")

    summary = asyncio.run(run(prospects, demo=args.demo, use_llm=use_llm))

    with open(args.out, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nFull report → {args.out}")
    total = sum(p["hits_surfaced"] for p in summary["prospects"])
    print(f"Total hits surfaced across all prospects: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
