"""Tests for the live UI endpoints — dashboard + hit cache."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from newton.main import app
from newton.store import hits as hits_store


client = TestClient(app)


def test_owners_list():
    r = client.get("/current-events")
    assert r.status_code == 200
    data = r.json()
    assert {"o_dan", "o_kim", "o_marco"}.issubset({o["id"] for o in data["items"]})


def test_dashboard_for_owner():
    r = client.get("/current-events/o_dan")
    assert r.status_code == 200
    data = r.json()
    assert data["owner"]["id"] == "o_dan"
    assert isinstance(data["prospects"], list)
    assert isinstance(data["recommendations"], list)
    assert isinstance(data["watchlists"], list)
    assert "stats" in data
    # Dan has 3 prospects
    assert data["stats"]["total"] >= 3


def test_dashboard_hits_attached():
    """Seed hits load and attach to prospects."""
    r = client.get("/current-events/o_dan")
    data = r.json()
    p_001 = next(p for p in data["prospects"] if p["id"] == "p_001")
    assert len(p_001["hits"]) >= 1
    h = p_001["hits"][0]
    assert "signal_category" in h
    assert "freshness_status" in h
    assert "title" in h


def test_dashboard_404_unknown_owner():
    r = client.get("/current-events/o_nope")
    assert r.status_code == 404


def test_healthz_includes_llm_and_hit_count():
    r = client.get("/healthz")
    data = r.json()
    assert data["ok"] is True
    assert "llm_configured" in data
    assert "cached_hits" in data


def test_root_serves_ui():
    r = client.get("/")
    assert r.status_code == 200
    body = r.text
    assert "Newton" in body and ("Current Events" in body or "current-events" in body)


def test_hits_cache_seeded():
    """The seed file ships with hits for the demo prospects."""
    assert hits_store.total_count() >= 5
