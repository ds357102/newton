"""Freshness gate.

Default: hyper-current (< 14d surfaces freely; 14–60d only if score >= 0.85;
older suppressed).
Cold-start exception: newly-added prospects with no archive get a wider window.
Archive de-duplication: an item already in ALF notes/freight intel is suppressed.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from .source import Prospect


FreshnessStatus = Literal["current", "cold_start", "aged_high_signal", "suppressed"]
WIDE_CATEGORIES = {"procurement", "partnerships", "facilities", "investments"}


@dataclass
class FreshnessDecision:
    status: FreshnessStatus
    reason: str
    archive_match: str | None = None


def url_hash(url: str) -> str:
    """Light-weight hash for archive lookup. Real impl: sha1(normalized_url)."""
    import hashlib
    return hashlib.sha1(url.encode()).hexdigest()[:10]


def evaluate(
    *,
    prospect: Prospect | None,
    ts_published: datetime | None,
    score: float,
    signal_category: str,
    url: str | None = None,
    now: datetime | None = None,
) -> FreshnessDecision:
    now = now or datetime.utcnow()

    # Archive dedupe first.
    if url and prospect:
        h = url_hash(url)
        if h in prospect.archive_url_hashes:
            return FreshnessDecision(status="suppressed", reason="already in archive", archive_match=h)

    if ts_published is None:
        return FreshnessDecision(status="current", reason="no timestamp; treated as fresh")

    age_days = (now - ts_published).days

    # Cold-start exception
    if prospect and prospect.is_cold_start:
        if age_days <= 180:
            return FreshnessDecision(status="cold_start", reason=f"new account, {age_days}d old")
        if age_days <= 365 and signal_category in WIDE_CATEGORIES:
            return FreshnessDecision(status="cold_start",
                                     reason=f"new account + high-value category ({signal_category})")
        return FreshnessDecision(status="suppressed", reason=f"new account but >12mo old")

    # Default rules
    if age_days < 14:
        return FreshnessDecision(status="current", reason=f"{age_days}d old")
    if age_days < 60 and score >= 0.85:
        return FreshnessDecision(status="aged_high_signal",
                                 reason=f"{age_days}d old, high score {score:.2f}")
    return FreshnessDecision(status="suppressed", reason=f"{age_days}d old, below threshold")
