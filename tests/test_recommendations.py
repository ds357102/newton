"""Tests for the recommendations engine."""
import pytest

from newton.recommendations.engine import engine, RecommendationEngine, QUIET_THRESHOLD


@pytest.mark.asyncio
async def test_engine_returns_seed_when_no_overlap():
    recs = await engine.for_owner("o_dan", limit=6)
    assert len(recs) >= 1
    assert all(r.signal_category in {"facilities", "investments", "partnerships", "products"}
               for r in recs)
    assert all(r.score >= 0.7 for r in recs)


@pytest.mark.asyncio
async def test_engine_excludes_companies_already_on_a_list():
    e = RecommendationEngine()
    # Artificially overlap by adding a Prospect whose name matches a seed entry
    from newton.prospects.source import prospect_source
    # 'Riverbend Polymers' is in the seed — pretend it's already a prospect
    from newton.prospects.source import Prospect
    from datetime import datetime
    fake = Prospect(id="z_fake", owner_id="o_dan", name="Riverbend Polymers", priority=False,
                    added_at=datetime.utcnow(), last_touch_at=None)
    prospect_source._sample.append(fake)
    try:
        recs = await e.for_owner("o_dan", limit=10)
        assert all(r.company_name != "Riverbend Polymers" for r in recs)
    finally:
        prospect_source._sample.pop()


@pytest.mark.asyncio
async def test_engine_sorted_by_score():
    recs = await engine.for_owner("o_kim", limit=6)
    scores = [r.score for r in recs]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_should_recommend_threshold():
    assert await engine.should_recommend("o_kim", surfaced_hits_last_24h=0) is True
    assert await engine.should_recommend("o_kim", surfaced_hits_last_24h=QUIET_THRESHOLD) is False
