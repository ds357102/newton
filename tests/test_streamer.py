"""Tests for the streamer's attribution logic (no network)."""
from __future__ import annotations
from datetime import datetime, timedelta

import pytest

from workers.streamer import attribute_to_prospects, INDUSTRY_FEEDS, REDDIT_FEEDS
from newton.prospects.source import Prospect


def _p(name, aliases=None, domains=None):
    return Prospect(
        id=f"p_{name.lower().replace(' ', '_')}",
        owner_id="o_test",
        name=name,
        priority=False,
        added_at=datetime.utcnow() - timedelta(days=60),
        last_touch_at=None,
        dba_aliases=aliases or [],
        domains=domains or [],
    )


def test_attribution_matches_by_name():
    p = _p("Tyson Foods")
    item = {"title": "Tyson Foods opens new processing plant",
            "excerpt": "Major announcement..."}
    matches = attribute_to_prospects(item, [p])
    assert matches == [p]


def test_attribution_matches_by_alias():
    # Aliases must be >= 4 chars (the filter avoids matching tiny common words).
    p = _p("Stanley Black & Decker", aliases=["Stanley B&D"])
    item = {"title": "Stanley B&D announces fleet expansion",
            "excerpt": "..."}
    matches = attribute_to_prospects(item, [p])
    assert matches == [p]


def test_attribution_matches_by_domain():
    p = _p("Acme Logistics", domains=["acmelogistics.com"])
    item = {"title": "Industry roundup",
            "excerpt": "See acmelogistics.com for details on the new lane."}
    matches = attribute_to_prospects(item, [p])
    assert matches == [p]


def test_attribution_no_match_when_unrelated():
    p = _p("Tyson Foods")
    item = {"title": "Random news about something else",
            "excerpt": "Nothing relevant here."}
    assert attribute_to_prospects(item, [p]) == []


def test_attribution_matches_multiple_prospects_in_same_article():
    a = _p("Acme Co")
    b = _p("Globex Corp")
    item = {"title": "Acme Co and Globex Corp announce joint venture",
            "excerpt": "..."}
    matches = attribute_to_prospects(item, [a, b])
    assert set(m.id for m in matches) == {a.id, b.id}


def test_attribution_ignores_short_terms():
    """Three-character names would over-match common words. Filtered out."""
    p = _p("AB", aliases=["XY"])
    item = {"title": "Article about ab tests in industry",
            "excerpt": "..."}
    assert attribute_to_prospects(item, [p]) == []


def test_industry_feeds_list_is_populated():
    assert len(INDUSTRY_FEEDS) >= 30
    for name, url in INDUSTRY_FEEDS:
        assert name and url.startswith("http")


def test_reddit_feeds_list_is_populated():
    assert len(REDDIT_FEEDS) >= 15
    for name, url in REDDIT_FEEDS:
        assert name.startswith("r/")
        assert "reddit.com" in url
        assert url.endswith(".rss")
