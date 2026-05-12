"""Prospect monitor — the orchestration layer.

For each prospect on ALF's list, expand its query bundle, run it across the
ingestion workers, score for buying signals, apply the freshness gate, and emit
events tagged with prospect_id + signal_category + freshness_status.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import AsyncIterator

from ..events import Event
from ..scoring.rules import score_rules
from ..scoring.llm import score_and_classify as llm_score_and_classify
from .source import Prospect, prospect_source
from .signals import classify, SignalCategory, CATEGORY_SCORE_BOOST
from .freshness import evaluate, FreshnessDecision


@dataclass
class ProspectHit:
    event: Event
    prospect: Prospect
    signal_category: SignalCategory
    matched_cues: list[str]
    freshness: FreshnessDecision


def annotate(event: Event, prospect: Prospect) -> ProspectHit:
    """Score, classify, and freshness-gate a single event for a prospect."""
    title = event.payload.get("title", "")
    excerpt = event.payload.get("excerpt", "")
    text = f"{title} {excerpt}"

    base_score, score_reason = score_rules(event, watchlist_terms=prospect.query_bundle())

    category, cues = classify(text)

    # Category-aware score boost: an item that classifies into a buying-signal
    # category is more relevant than a generic mention of the same prospect.
    # Without this, real buying signals get suppressed by the 14–60d freshness
    # gate (which needs score >= 0.85). v0.5 LLM scorer will replace this heuristic.
    category_boost = CATEGORY_SCORE_BOOST.get(category, 0.0)
    score = min(1.0, base_score + category_boost)

    event.score = score
    event.score_reason = (
        f"{score_reason}; category={category} (+{category_boost:.2f})"
        if category_boost > 0 else score_reason
    )

    event.tags = list({*event.tags, f"prospect:{prospect.id}", f"signal:{category}"})
    event.payload["prospect_id"] = prospect.id
    event.payload["signal_category"] = category

    decision = evaluate(
        prospect=prospect,
        ts_published=event.ts_published,
        score=score,
        signal_category=category,
        url=event.payload.get("url"),
    )
    event.payload["freshness_status"] = decision.status
    event.payload["freshness_reason"] = decision.reason
    if decision.archive_match:
        event.payload["archive_match_id"] = decision.archive_match

    return ProspectHit(
        event=event, prospect=prospect,
        signal_category=category, matched_cues=cues,
        freshness=decision,
    )


async def annotate_with_llm(event: Event, prospect: Prospect) -> ProspectHit:
    """Run rules first, then enrich with the LLM pass when available.

    Behavior:
      - Always runs the rules-based annotate() first (fast, free, deterministic).
      - Calls the LLM. If it returns a result, that result overrides the rules:
        score, category, and the freshness gate get recomputed using the LLM's
        numbers. The LLM's key_phrases become the matched_cues.
      - If the LLM returns None (no API key / SDK missing / call failed), the
        rules-based hit is returned unchanged.
    """
    hit = annotate(event, prospect)

    llm = await llm_score_and_classify(event, prospect.name, prospect.industry)
    if llm is None:
        return hit

    # LLM result takes precedence. Re-tag, re-score, re-gate.
    event.score = llm.score
    event.score_reason = f"llm:{llm.reason}"
    event.payload["signal_category"] = llm.category
    event.payload["llm_reason"] = llm.reason
    event.payload["llm_key_phrases"] = llm.key_phrases
    event.tags = list({
        *(t for t in event.tags if not t.startswith("signal:")),
        f"prospect:{prospect.id}",
        f"signal:{llm.category}",
    })

    decision = evaluate(
        prospect=prospect,
        ts_published=event.ts_published,
        score=llm.score,
        signal_category=llm.category,
        url=event.payload.get("url"),
    )
    event.payload["freshness_status"] = decision.status
    event.payload["freshness_reason"] = decision.reason
    if decision.archive_match:
        event.payload["archive_match_id"] = decision.archive_match

    return ProspectHit(
        event=event, prospect=prospect,
        signal_category=llm.category,
        matched_cues=llm.key_phrases or hit.matched_cues,
        freshness=decision,
    )


async def run_for_all_prospects(events_per_prospect: dict[str, list[Event]],
                                use_llm: bool = True) -> list[ProspectHit]:
    """Annotate a batch of events keyed by prospect_id.

    Returns only hits that survive the freshness gate (status != 'suppressed').
    """
    hits: list[ProspectHit] = []
    prospects = await prospect_source.all()
    for prospect in prospects:
        for ev in events_per_prospect.get(prospect.id, []):
            hit = await annotate_with_llm(ev, prospect) if use_llm else annotate(ev, prospect)
            if hit.freshness.status != "suppressed":
                hits.append(hit)
    return hits
