"""Tests for the LLM classifier + relevance scorer (v0.5).

We never hit a real API in tests — score_and_classify is mocked. Two paths
matter: (a) LLM returns a result and overrides the rules; (b) LLM returns None
and the rules result is preserved.
"""
from __future__ import annotations
from datetime import datetime, timedelta

import pytest

from newton.events import Event
from newton.prospects.source import prospect_source
from newton.prospects.monitor import annotate_with_llm
from newton.scoring.llm import LLMResult, _strip_fences, clear_cache


@pytest.fixture(autouse=True)
def _clear_llm_cache():
    clear_cache()
    yield
    clear_cache()


@pytest.mark.asyncio
async def test_llm_overrides_rules(monkeypatch):
    """When the LLM returns a result, score + category + freshness use it."""
    from newton.prospects import monitor

    async def fake_llm(event, prospect_name, prospect_industry=None, **kw):
        return LLMResult(
            score=0.95, category="facilities",
            reason="New processing plant; clear footprint expansion.",
            key_phrases=["new plant", "Arkansas", "Q2 production"],
        )
    monkeypatch.setattr(monitor, "llm_score_and_classify", fake_llm)

    p = await prospect_source.get("p_001")
    ev = Event(
        source="rss",
        ts_published=datetime.utcnow() - timedelta(days=3),
        payload={
            "title": "Acme announces something in Arkansas",
            "excerpt": "Generic excerpt with no obvious rules cues.",
            "url": "https://example.com/llm-override",
        },
    )
    hit = await annotate_with_llm(ev, p)
    assert hit.signal_category == "facilities"
    assert hit.event.score == 0.95
    assert hit.freshness.status == "current"
    assert "new plant" in hit.matched_cues
    assert hit.event.payload["llm_reason"].startswith("New processing")
    # Tag rewrites cleanly — only one signal: tag should remain.
    signal_tags = [t for t in hit.event.tags if t.startswith("signal:")]
    assert signal_tags == ["signal:facilities"]


@pytest.mark.asyncio
async def test_llm_none_keeps_rules_result(monkeypatch):
    """When LLM returns None, the rules-based hit is preserved untouched."""
    from newton.prospects import monitor

    async def fake_llm(event, prospect_name, prospect_industry=None, **kw):
        return None
    monkeypatch.setattr(monitor, "llm_score_and_classify", fake_llm)

    p = await prospect_source.get("p_001")
    ev = Event(
        source="rss",
        ts_published=datetime.utcnow() - timedelta(days=3),
        payload={
            "title": f"{p.name} files RFP for 2026 lane awards",
            "excerpt": "Procurement memo, carrier-bid window opens next quarter.",
            "url": "https://example.com/rules-only",
        },
    )
    hit = await annotate_with_llm(ev, p)
    assert hit.signal_category == "procurement"  # rules caught it
    assert hit.event.score >= 0.85               # rules + category boost


@pytest.mark.asyncio
async def test_llm_re_gates_freshness_with_new_score(monkeypatch):
    """If the LLM lifts an aged item above the threshold, freshness re-evaluates."""
    from newton.prospects import monitor

    async def fake_llm(event, prospect_name, prospect_industry=None, **kw):
        return LLMResult(score=0.92, category="investments",
                         reason="$200M capex.", key_phrases=["capex"])
    monkeypatch.setattr(monitor, "llm_score_and_classify", fake_llm)

    p = await prospect_source.get("p_001")
    ev = Event(
        source="rss",
        ts_published=datetime.utcnow() - timedelta(days=40),  # would suppress at low score
        payload={
            "title": "Acme announces $200M capex",
            "excerpt": "Capital plan...",
            "url": "https://example.com/aged-capex",
        },
    )
    hit = await annotate_with_llm(ev, p)
    assert hit.freshness.status == "aged_high_signal"


def test_strip_fences_handles_json_codeblock():
    assert _strip_fences('```json\n{"score": 0.9}\n```') == '{"score": 0.9}'
    assert _strip_fences('```\n{"a": 1}\n```') == '{"a": 1}'
    assert _strip_fences('{"a": 1}') == '{"a": 1}'


def test_strip_fences_handles_extra_whitespace():
    assert _strip_fences('   {"a": 1}   ') == '{"a": 1}'


@pytest.mark.asyncio
async def test_llm_disabled_when_no_key():
    """With no ANTHROPIC_API_KEY in settings, the real fn short-circuits to None."""
    from newton.scoring import llm
    from newton.config import settings
    # The test env has no key configured, so this should return None.
    assert settings.anthropic_api_key in (None, "")
    result = await llm.score_and_classify(
        Event(source="rss", payload={"title": "x", "url": "y"}),
        prospect_name="Test Co",
    )
    assert result is None
