"""Tests for the prospect monitor module."""
from __future__ import annotations
from datetime import datetime, timedelta

import pytest

from newton.events import Event
from newton.prospects.source import Prospect, prospect_source, AlfProspectSource
from newton.prospects.signals import classify
from newton.prospects.freshness import evaluate
from newton.prospects.monitor import annotate


# ---- signals classifier ----
@pytest.mark.parametrize("text,expected", [
    ("Acme issues new freight RFP for 2026 lane awards", "procurement"),
    ("NorthStar opens new Memphis distribution center", "facilities"),
    ("Harborline announces $40M capex investment in fleet", "investments"),
    ("Acme partners with Globex on exclusive distribution", "partnerships"),
    ("NorthStar rolls out new product line in Q3", "products"),
    ("CEO shuffle: Acme appoints new VP of Supply Chain", "major"),
    ("Random freight market commentary", "none"),
])
def test_classify(text, expected):
    cat, cues = classify(text)
    assert cat == expected
    assert cat == "none" or len(cues) >= 1


# ---- freshness gate ----
def test_freshness_default_fresh():
    p = next(iter([_p for _p in (lambda: __import__("asyncio").run(prospect_source.all()))()]))
    d = evaluate(prospect=p, ts_published=datetime.utcnow() - timedelta(days=3),
                 score=0.5, signal_category="facilities", url="https://example.com/a")
    assert d.status == "current"


def test_freshness_aged_high_signal():
    p = next(iter([_p for _p in (lambda: __import__("asyncio").run(prospect_source.all()))()]))
    d = evaluate(prospect=p, ts_published=datetime.utcnow() - timedelta(days=30),
                 score=0.92, signal_category="facilities", url="https://example.com/b")
    assert d.status == "aged_high_signal"


def test_freshness_suppressed_aged_low_score():
    p = next(iter([_p for _p in (lambda: __import__("asyncio").run(prospect_source.all()))()]))
    d = evaluate(prospect=p, ts_published=datetime.utcnow() - timedelta(days=30),
                 score=0.5, signal_category="major", url="https://example.com/c")
    assert d.status == "suppressed"


def test_freshness_cold_start_window():
    cold = Prospect(id="cold", owner_id="o_test", name="Cold Co", priority=True,
                    added_at=datetime.utcnow() - timedelta(days=3),
                    last_touch_at=None, archive_url_hashes=set())
    d = evaluate(prospect=cold, ts_published=datetime.utcnow() - timedelta(days=120),
                 score=0.4, signal_category="major", url="https://example.com/d")
    assert d.status == "cold_start"


def test_freshness_cold_start_high_value_category_extends_to_year():
    cold = Prospect(id="cold", owner_id="o_test", name="Cold Co", priority=True,
                    added_at=datetime.utcnow() - timedelta(days=3),
                    last_touch_at=None, archive_url_hashes=set())
    d = evaluate(prospect=cold, ts_published=datetime.utcnow() - timedelta(days=300),
                 score=0.4, signal_category="procurement", url="https://example.com/e")
    assert d.status == "cold_start"


def test_freshness_archive_dedupe():
    from newton.prospects.freshness import url_hash
    url = "https://example.com/already-filed"
    p = Prospect(id="x", owner_id="o_test", name="X Co", priority=False,
                 added_at=datetime.utcnow() - timedelta(days=200),
                 last_touch_at=None, archive_url_hashes={url_hash(url)})
    d = evaluate(prospect=p, ts_published=datetime.utcnow() - timedelta(days=2),
                 score=0.95, signal_category="facilities", url=url)
    assert d.status == "suppressed"
    assert d.archive_match is not None


# ---- annotate (end-to-end, single event) ----
@pytest.mark.asyncio
async def test_annotate_tags_event_with_prospect_and_signal():
    p = await prospect_source.get("p_002")  # cold-start prospect
    ev = Event(
        source="rss",
        ts_published=datetime.utcnow() - timedelta(days=3),
        payload={"title": "NorthStar opens new Memphis distribution center",
                 "excerpt": "Major DC expansion targets Q3 ribbon-cutting",
                 "url": "https://example.com/northstar-dc"},
    )
    hit = annotate(ev, p)
    assert hit.signal_category == "facilities"
    assert hit.freshness.status in ("current", "cold_start")
    assert f"prospect:{p.id}" in ev.tags
    assert "signal:facilities" in ev.tags
    assert ev.payload["prospect_id"] == p.id


# ---- prospect source ----
@pytest.mark.asyncio
async def test_priority_filter():
    src = AlfProspectSource()
    pri = await src.priority()
    assert all(p.priority for p in pri)
    assert len(pri) >= 1


# ---- per-owner ----
@pytest.mark.asyncio
async def test_for_owner_returns_only_owners_prospects():
    dan = await prospect_source.for_owner("o_dan")
    assert all(p.owner_id == "o_dan" for p in dan)
    assert len(dan) >= 1


@pytest.mark.asyncio
async def test_owners_listed():
    owners = await prospect_source.owners()
    ids = {o.id for o in owners}
    assert {"o_dan", "o_kim", "o_marco"}.issubset(ids)


# ---- category score boost (v0.4) ----
@pytest.mark.asyncio
async def test_category_boost_lifts_procurement_above_freshness_threshold():
    """A procurement-classified item 22 days old should survive the 14-60d gate."""
    p = await prospect_source.get("p_001")
    ev = Event(
        source="rss",
        ts_published=datetime.utcnow() - timedelta(days=22),
        payload={
            "title": f"{p.name} files RFP for 2026 lane awards",
            "excerpt": "Internal procurement memo opens carrier-bid window next quarter.",
            "url": "https://example.com/rfp-test",
        },
    )
    hit = annotate(ev, p)
    assert hit.signal_category == "procurement"
    assert hit.event.score >= 0.85, f"expected >=0.85 after boost, got {hit.event.score}"
    assert hit.freshness.status == "aged_high_signal"


@pytest.mark.asyncio
async def test_uncategorized_item_does_not_get_boost():
    """A 'none' classification gets no boost, so the score is the raw rules score."""
    p = await prospect_source.get("p_001")
    ev = Event(
        source="rss",
        ts_published=datetime.utcnow() - timedelta(days=2),
        payload={
            "title": f"Generic mention of {p.name} in a feature piece",
            "excerpt": "Industry retrospective with no specific buying signal.",
            "url": "https://example.com/generic",
        },
    )
    hit = annotate(ev, p)
    assert hit.signal_category == "none"
    assert hit.event.score < 0.85
