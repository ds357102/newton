"""Smoke tests — every module imports, the FastAPI app exposes its routes, scoring runs."""
import importlib
import pytest


MODULES = [
    "newton",
    "newton.config",
    "newton.events",
    "newton.main",
    "newton.api.ticker", "newton.api.feed", "newton.api.watchlists",
    "newton.api.ideas", "newton.api.automation",
    "newton.ticker.service", "newton.ticker.adapters.base", "newton.ticker.adapters.mock",
    "newton.ingestion.base", "newton.ingestion.reddit", "newton.ingestion.x",
    "newton.ingestion.linkedin", "newton.ingestion.rss", "newton.ingestion.web",
    "newton.scoring.rules", "newton.scoring.llm",
    "newton.watchlists.registry",
    "newton.ideas.vault", "newton.ideas.drafting",
    "newton.automation.tiers",
    "newton.store.hits",
    "newton.api.dashboard",
    "newton.api.alf_actions",
    "newton.api.voice",
    "newton.integrations.alf",
    "newton.voice.profiles",
    "newton.api.recommendations",
    "newton.recommendations.engine",
    "newton.prospects.monitor",
    "newton.prospects.freshness",
    "newton.prospects.signals",
    "newton.prospects.source",
    "newton.ingestion.youtube",
    "newton.api.prospects",
]


@pytest.mark.parametrize("mod", MODULES)
def test_module_imports(mod):
    importlib.import_module(mod)


def test_app_routes():
    from newton.main import app
    paths = {r.path for r in app.routes}
    for needed in {"/healthz", "/ticker", "/feed", "/watchlists", "/ideas", "/automation", "/prospects", "/recommendations", "/voice/profiles", "/alf/notes", "/current-events"}:
        assert needed in paths, f"missing route {needed}"


def test_score_rules_runs():
    from newton.events import Event
    from newton.scoring.rules import score_rules
    ev = Event(source="rss", payload={"title": "Freight rates jump", "excerpt": "logistics update"})
    s, _ = score_rules(ev, ["freight"])
    assert 0 <= s <= 1


def test_watchlist_registry_seeded():
    from newton.watchlists.registry import registry
    assert len(registry.all()) >= 2
