"""Tests for v0.6 outreach drafting + voice profiles + ALF stub."""
from __future__ import annotations
from dataclasses import asdict

import pytest

from newton.voice.profiles import registry as voice_registry, DEFAULT_AVOID
from newton.ideas.drafting import (
    generate_outreach_draft, draft_outreach, DraftResult,
)
from newton.ideas.vault import vault
from newton.integrations.alf import client as alf_client


# ---- voice profiles ----
def test_voice_profiles_seeded_per_owner_per_channel():
    profiles = voice_registry.all()
    by_owner = {}
    for p in profiles:
        by_owner.setdefault(p.owner_id, set()).add(p.channel)
    # Each demo owner should have all three channels.
    for owner_id, channels in by_owner.items():
        assert {"linkedin", "email", "phone"}.issubset(channels), \
            f"{owner_id} missing channels: {channels}"


def test_voice_profile_update():
    p = voice_registry.all()[0]
    updated = voice_registry.update(p.id, tone="consultative", signature="— D.")
    assert updated.tone == "consultative"
    assert updated.signature == "— D."


# ---- generate_outreach_draft with mocked LLM ----
@pytest.mark.asyncio
async def test_generate_outreach_draft_mocked(monkeypatch):
    """Patch the Anthropic client to return a canned JSON response."""
    fake_response_text = (
        '{"subject": null, "body": "Saw the Memphis DC. Quick read on outbound capacity if useful.", '
        '"cta": "Want a 10-minute lay of the land?", "voice_score": 0.82, "voice_check_notes": "clean"}'
    )

    class FakeContent:
        def __init__(self, text): self.text = text

    class FakeResp:
        def __init__(self): self.content = [FakeContent(fake_response_text)]

    class FakeMessages:
        async def create(self, **kw): return FakeResp()

    class FakeClient:
        def __init__(self, **kw): self.messages = FakeMessages()

    from newton.ideas import drafting
    monkeypatch.setattr(drafting, "AsyncAnthropic", FakeClient, raising=False)
    monkeypatch.setattr(drafting, "_ANTHROPIC_AVAILABLE", True)
    from newton.config import settings as cfg
    monkeypatch.setattr(cfg, "anthropic_api_key", "sk-test")

    result = await generate_outreach_draft(
        prospect={"name": "NorthStar Foods", "industry": "food mfg",
                  "priority": True, "is_cold_start": True},
        signal={"title": "NorthStar opens new Memphis distribution center",
                "excerpt": "Q3 ribbon-cutting; refrigerated outbound up materially.",
                "signal_category": "facilities",
                "reason": "facilities expansion",
                "key_phrases": ["DC", "Memphis"]},
        channel="linkedin",
        owner_id="o_dan",
    )
    assert isinstance(result, DraftResult)
    assert result.subject is None
    assert "Memphis" in result.body
    assert result.cta
    assert 0.0 <= result.voice_score <= 1.0
    assert result.is_stub is False


@pytest.mark.asyncio
async def test_avoid_phrase_penalty(monkeypatch):
    """If the LLM slips a bot-tell into the body, the local voice check
    knocks the score down and flags it in notes."""
    fake_text = (
        '{"subject": "x", "body": "I hope this email finds you well — saw the news.", '
        '"cta": "Open to a 15-min call?", "voice_score": 0.9, "voice_check_notes": ""}'
    )

    class FakeContent:
        def __init__(self, text): self.text = text
    class FakeResp:
        def __init__(self): self.content = [FakeContent(fake_text)]
    class FakeMessages:
        async def create(self, **kw): return FakeResp()
    class FakeClient:
        def __init__(self, **kw): self.messages = FakeMessages()

    from newton.ideas import drafting
    monkeypatch.setattr(drafting, "AsyncAnthropic", FakeClient, raising=False)
    monkeypatch.setattr(drafting, "_ANTHROPIC_AVAILABLE", True)
    from newton.config import settings as cfg
    monkeypatch.setattr(cfg, "anthropic_api_key", "sk-test")

    result = await generate_outreach_draft(
        prospect={"name": "Acme", "industry": "logistics", "priority": True, "is_cold_start": False},
        signal={"title": "x", "excerpt": "y", "signal_category": "procurement"},
        channel="email",
        owner_id="o_dan",
    )
    assert result.voice_score <= 0.4, "avoid-phrase should knock score down"
    assert "hope this email finds you well" in result.voice_check_notes.lower()


@pytest.mark.asyncio
async def test_stub_draft_when_no_key():
    """No ANTHROPIC_API_KEY → return clearly-marked stub, don't crash."""
    result = await generate_outreach_draft(
        prospect={"name": "Test Co", "industry": "x"},
        signal={"title": "y", "signal_category": "facilities"},
        channel="linkedin",
        owner_id="o_dan",
    )
    assert result.is_stub is True
    assert "[stub" in result.body


# ---- draft_outreach (entry point) ----
@pytest.mark.asyncio
async def test_draft_outreach_returns_dict():
    result = await draft_outreach(
        prospect={"name": "Acme", "industry": "3PL"},
        signal={"title": "x", "signal_category": "procurement"},
        channel="linkedin",
        owner_id="o_dan",
    )
    assert isinstance(result, dict)
    assert "body" in result
    assert "channel" in result


# ---- ALF stub ----
def test_alf_notes_enqueue_and_drain():
    n = alf_client.send_note(
        prospect_id="p_001", owner_id="o_dan",
        title="Memphis DC follow-up", body="Saved this for outreach.",
        source_url="https://example.com/x",
    )
    assert n.status == "pending"
    pending = alf_client.pending(owner_id="o_dan")
    assert any(p.id == n.id for p in pending)
    # drain is a no-op until v1.0
    assert alf_client.drain_to_alf() == 0
