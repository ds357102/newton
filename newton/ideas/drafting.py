"""LLM-driven outreach drafting (v0.6).

Two entry points:
  - draft_outreach(prospect, signal, channel, owner_id) — direct from prospect
    card / pipeline; no Idea record required.
  - draft_for_idea(idea_id, channel) — backed by an existing idea record.

Both call into generate_outreach_draft(). The LLM prompt enforces:
  - Reference the specific signal, not generic flattery.
  - Don't fake a relationship.
  - Avoid bot-tells listed in the owner's voice profile.
  - Tight word limits per channel.

Falls back to a clearly-marked stub draft when ANTHROPIC_API_KEY is missing.
"""
from __future__ import annotations
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional

from ..config import settings
from ..voice.profiles import VoiceProfile, registry as voice_registry
from .vault import vault

log = logging.getLogger("newton.ideas.drafting")

try:
    from anthropic import AsyncAnthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False


DEFAULT_MODEL = "claude-haiku-4-5-20251001"


@dataclass
class DraftResult:
    channel: str
    subject: str | None
    body: str
    cta: str
    voice_score: float
    voice_check_notes: str
    version: int
    generated_at: str
    model: str | None = None
    is_stub: bool = False


SYSTEM_PROMPT = """\
You are drafting a first-touch outreach message for a freight broker reaching
out to a prospect company. The broker spotted a specific buying signal in the
prospect's recent news and is using that as a credible reason to start a conversation.

Hard rules:
- Reference the specific signal. Don't be generic.
- Don't fake a relationship that doesn't exist.
- Don't claim to have worked with this prospect before unless told otherwise.
- Avoid every phrase listed in the "Avoid" section verbatim.
- Stay within the word limit.
- For LINKEDIN: no formal salutation or signoff. No "Dear ___". No "Best regards".
- For EMAIL: include a subject line. Subject is short, specific, no clickbait.
- For PHONE: produce a talking-point opener (2–3 sentences) plus a pivot if pushed.
- End with a low-friction CTA — a question, a short specific offer, or a piece
  of useful intel. Never "would love to learn more about your business."

Output ONLY a JSON object, no prose, no code fences:
{
  "subject": "<for email; null otherwise>",
  "body": "<the message>",
  "cta": "<one-sentence call to action>",
  "voice_score": 0.0-1.0,
  "voice_check_notes": "<flag if anything drifted from voice or hit an avoid-phrase>"
}
"""


def _build_user_prompt(profile: VoiceProfile, prospect: dict, signal: dict) -> str:
    anchors = "\n".join(f"  - {a}" for a in (profile.sample_anchors or []))
    avoid = ", ".join(f'"{a}"' for a in profile.avoid_phrases)
    parts = [
        f"Channel: {profile.channel}",
        f"Tone: {profile.tone}",
        f"Word limit: {profile.word_limit}",
        f"Owner name: {profile.owner_name}",
        f"Agency name: {profile.agency_name}",
        f"Signature line (if used): {profile.signature}",
        "",
        "Sample anchors from past messages this owner liked:" + ("\n" + anchors if anchors else " (none)"),
        "",
        f"Avoid phrases: {avoid}",
        "",
        "--- Prospect ---",
        f"Name: {prospect.get('name')}",
        f"Industry: {prospect.get('industry') or 'unknown'}",
        f"Priority account: {prospect.get('priority', False)}",
        f"Cold-start (newly added): {prospect.get('is_cold_start', False)}",
        "",
        "--- Buying signal ---",
        f"Category: {signal.get('signal_category')}",
        f"Headline: {signal.get('title')}",
        f"Excerpt: {signal.get('excerpt')}",
        f"Why it matters: {signal.get('reason') or signal.get('score_reason')}",
        f"Key phrases: {signal.get('key_phrases') or signal.get('matched_cues')}",
    ]
    return "\n".join(parts)


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        parts = t.split("```")
        if len(parts) >= 2:
            t = parts[1]
            if t.startswith("json"):
                t = t[4:]
    return t.strip()


def _stub_draft(profile: VoiceProfile, prospect: dict, signal: dict, version: int) -> DraftResult:
    """No API key? Return a clearly-marked stub so the UI flow still works."""
    title = signal.get("title", "the recent announcement")
    body = (
        f"[stub draft — no LLM key configured]\n"
        f"Channel: {profile.channel}; tone: {profile.tone}; prospect: {prospect.get('name')}; "
        f"signal: {signal.get('signal_category')}; headline: {title}"
    )
    return DraftResult(
        channel=profile.channel,
        subject="[stub subject]" if profile.channel == "email" else None,
        body=body,
        cta="[stub CTA]",
        voice_score=0.0,
        voice_check_notes="LLM disabled — generated stub draft.",
        version=version,
        generated_at=datetime.utcnow().isoformat() + "Z",
        is_stub=True,
    )


async def generate_outreach_draft(
    *,
    prospect: dict,
    signal: dict,
    channel: str,
    owner_id: str,
    profile: VoiceProfile | None = None,
    version: int = 1,
    model: str = DEFAULT_MODEL,
) -> DraftResult:
    """Generate a first-touch outreach draft. The dict shapes are loose so the
    function can be called directly from a prospect-card payload (a ProspectHit)
    or from a stored Idea + Event pair."""

    profile = profile or voice_registry.for_owner_channel(owner_id, channel)  # type: ignore[arg-type]
    if profile is None:
        # Fall back to a synthesized profile if none seeded yet.
        from ..voice.profiles import DEFAULT_AVOID
        profile = VoiceProfile(
            id="ephemeral", owner_id=owner_id, channel=channel,  # type: ignore[arg-type]
            tone="direct", owner_name="the owner", agency_name="the agency",
            signature="— the owner", sample_anchors=[],
            avoid_phrases=list(DEFAULT_AVOID),
            word_limit=150 if channel == "email" else 100,
        )

    if not settings.anthropic_api_key or not _ANTHROPIC_AVAILABLE:
        return _stub_draft(profile, prospect, signal, version)

    user_prompt = _build_user_prompt(profile, prospect, signal)

    try:
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        resp = await client.messages.create(
            model=model,
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = resp.content[0].text
        data = json.loads(_strip_fences(text))

        # Local voice check — penalize if any avoid-phrase slipped in.
        body = data.get("body", "")
        hits = [a for a in profile.avoid_phrases if a.lower() in body.lower()]
        voice_score = float(data.get("voice_score", 0.5))
        notes = data.get("voice_check_notes", "")
        if hits:
            voice_score = min(voice_score, 0.4)
            notes = (notes + " | local: hit avoid-phrases " + ", ".join(hits)).strip(" |")

        return DraftResult(
            channel=channel,
            subject=data.get("subject"),
            body=body,
            cta=data.get("cta", ""),
            voice_score=voice_score,
            voice_check_notes=notes,
            version=version,
            generated_at=datetime.utcnow().isoformat() + "Z",
            model=model,
        )
    except Exception as e:
        log.warning(f"outreach draft generation failed: {e}")
        return _stub_draft(profile, prospect, signal, version)


# ---- entry points ----
async def draft_outreach(*, prospect: dict, signal: dict, channel: str,
                         owner_id: str) -> dict:
    """Direct-from-prospect-card path. No Idea record required."""
    result = await generate_outreach_draft(
        prospect=prospect, signal=signal, channel=channel, owner_id=owner_id,
    )
    return asdict(result)


async def draft_for_idea(idea_id: str, *, channel: str = "linkedin") -> dict:
    """Idea-backed path. Looks up the idea, generates, appends to its drafts list."""
    idea = vault.get(idea_id)
    if not idea:
        return {"error": "idea not found"}

    # Idea payload should carry prospect + signal context the front-end stashed
    # when the user clicked "Save idea" on a prospect card. Fall back gracefully.
    prospect = idea.get("prospect") or {}
    signal = idea.get("signal") or {}
    owner_id = prospect.get("owner_id") or idea.get("owner_id") or "o_me"
    version = len(idea["drafts"]) + 1

    result = await generate_outreach_draft(
        prospect=prospect, signal=signal, channel=channel, owner_id=owner_id,
        version=version,
    )
    idea["drafts"].append(asdict(result))
    if idea["status"] in ("raw", "sketched"):
        idea["status"] = "drafted"
    return asdict(result)
