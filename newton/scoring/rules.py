"""Pass 1 — cheap rule-based relevance scorer. Runs on every event."""
from __future__ import annotations
from ..events import Event


KEYWORD_BOOST = {"freight": 0.1, "logistics": 0.08, "shipper": 0.08, "carrier": 0.05}


def score_rules(event: Event, watchlist_terms: list[str]) -> tuple[float, str]:
    title = (event.payload.get("title") or "").lower()
    excerpt = (event.payload.get("excerpt") or "").lower()
    text = f"{title} {excerpt}"

    score = 0.3
    reasons: list[str] = []

    for term in watchlist_terms:
        if term.lower() in text:
            score += 0.2
            reasons.append(f"watchlist:{term}")

    for kw, boost in KEYWORD_BOOST.items():
        if kw in text:
            score += boost
            reasons.append(f"kw:{kw}")

    score = min(score, 1.0)
    return score, "; ".join(reasons) or "baseline"
