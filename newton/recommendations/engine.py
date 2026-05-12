"""Recommendation engine: surface manufacturers in the news with active buying
signals, filtered to companies the owner is NOT already tracking.

v0.3 stub returns hand-picked plausible manufacturers so the empty-state UI is
testable end-to-end. v0.5 swaps to real entity extraction over the live feed:
  1. Take last 30 days of events, score >= 0.7
  2. Keep events whose signal_category is in {facilities, investments, partnerships, products}
  3. Extract company names (NER + a manufacturer/industrial classifier)
  4. Drop companies already on ANY owner's list
  5. Rank by signal recency + score; return top N
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from ..prospects.source import prospect_source

QUIET_THRESHOLD = 3  # if owner has fewer than N surfaced hits in last 24h, recommend


@dataclass
class Recommendation:
    company_name: str
    industry: str
    signal_category: Literal["facilities", "investments", "partnerships", "products"]
    headline: str
    excerpt: str
    source_url: str
    age_days: int
    score: float
    rationale: str  # short "why this is worth a look" line


# Hand-picked seed for v0.3. Swap to real extraction in v0.5.
SEED: list[Recommendation] = [
    Recommendation(
        company_name="Riverbend Polymers",
        industry="plastics manufacturing",
        signal_category="facilities",
        headline="Riverbend breaks ground on $180M Tennessee plant",
        excerpt="200-acre site in Knox County; first phase targets Q2 2027 production with hiring for ~250 roles.",
        source_url="https://example.com/riverbend-tn",
        age_days=4, score=0.92,
        rationale="New plant means new outbound freight programs from Q2 2027 — early conversation now is well-timed.",
    ),
    Recommendation(
        company_name="Cooperline Foods",
        industry="food manufacturing",
        signal_category="investments",
        headline="Cooperline announces $90M cold-storage capex through 2027",
        excerpt="Capacity build-out across three states; refrigerated freight spend expected to step up materially.",
        source_url="https://example.com/cooperline-capex",
        age_days=9, score=0.88,
        rationale="Capex on cold storage almost always pulls reefer freight RFPs within 6–12 months.",
    ),
    Recommendation(
        company_name="Northbay Mills",
        industry="paper / packaging",
        signal_category="partnerships",
        headline="Northbay Mills inks exclusive distribution deal with regional retailer",
        excerpt="Multi-year agreement covers seven states; new lane volume kicks in Q3.",
        source_url="https://example.com/northbay-deal",
        age_days=2, score=0.86,
        rationale="Exclusive distribution = predictable lane density. Carrier-bid window typically follows announcement by 60–90 days.",
    ),
    Recommendation(
        company_name="Ironforge Components",
        industry="industrial / metalworking",
        signal_category="facilities",
        headline="Ironforge expanding Cincinnati machining facility",
        excerpt="Adding 120,000 sq ft and a second shift; supplier ecosystem briefing scheduled for next month.",
        source_url="https://example.com/ironforge-expand",
        age_days=11, score=0.83,
        rationale="Machining expansions pull both inbound raw-material freight and finished-goods outbound.",
    ),
    Recommendation(
        company_name="Solis Battery",
        industry="battery / energy manufacturing",
        signal_category="products",
        headline="Solis launches new commercial-grade battery line",
        excerpt="Commercial-vehicle and stationary-storage variants; pilot deployments shipping this quarter.",
        source_url="https://example.com/solis-launch",
        age_days=6, score=0.80,
        rationale="New product launches in regulated manufacturing usually trigger fresh logistics provider review.",
    ),
    Recommendation(
        company_name="Vellum Print",
        industry="commercial print",
        signal_category="investments",
        headline="Vellum Print closes $40M growth round, opens second plant",
        excerpt="Funding earmarked for a Texas plant and fleet expansion.",
        source_url="https://example.com/vellum-round",
        age_days=14, score=0.79,
        rationale="Growth round + fleet line item is an explicit logistics-investment signal.",
    ),
]


class RecommendationEngine:
    """Stub-backed recommendation engine. Real entity extraction lands in v0.5."""

    def __init__(self) -> None:
        self._seed = list(SEED)

    async def for_owner(self, owner_id: str, limit: int = 6) -> list[Recommendation]:
        """Return manufacturers worth a first look, excluding any already on
        any owner's list (so an owner doesn't get recommended someone a colleague
        is already calling on)."""
        all_prospects = await prospect_source.all()
        on_someones_list = {p.name.lower() for p in all_prospects}
        results = [
            r for r in self._seed
            if r.company_name.lower() not in on_someones_list
        ]
        results.sort(key=lambda r: (r.score, -r.age_days), reverse=True)
        return results[:limit]

    async def should_recommend(self, owner_id: str, surfaced_hits_last_24h: int) -> bool:
        return surfaced_hits_last_24h < QUIET_THRESHOLD


engine = RecommendationEngine()
