"""Recommendations API — surface manufacturers worth a first look.

Quiet-day fallback for the prospect feed: when an owner has < QUIET_THRESHOLD
surfaced hits in the last 24h, the UI shows this list instead of an empty state.
"""
from fastapi import APIRouter, Query

from ..recommendations.engine import engine

router = APIRouter()


@router.get("")
async def list_recommendations(
    owner_id: str = Query(...),
    limit: int = Query(default=6, le=20),
):
    recs = await engine.for_owner(owner_id, limit=limit)
    return {
        "owner_id": owner_id,
        "items": [
            {
                "company_name": r.company_name,
                "industry": r.industry,
                "signal_category": r.signal_category,
                "headline": r.headline,
                "excerpt": r.excerpt,
                "source_url": r.source_url,
                "age_days": r.age_days,
                "score": r.score,
                "rationale": r.rationale,
            }
            for r in recs
        ],
    }
