"""Voice profile registry.

Each account owner has one profile per channel (linkedin / email / phone).
Profiles feed the LLM drafting prompt so generated outreach matches the owner's
actual voice, and so it dodges the bot-tells listed in `avoid_phrases`.

v0.6 stores profiles in memory with sensible defaults. v0.7 backs by Postgres
and starts learning from "Mark not relevant" / accepted-draft feedback.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal
from uuid import uuid4

Channel = Literal["linkedin", "email", "phone"]


# Bot-tells to avoid. Drafts get a voice-score penalty if any of these slip in.
DEFAULT_AVOID = [
    "I hope this email finds you well",
    "I hope this finds you well",
    "I came across your company",
    "I wanted to reach out",
    "I'd love to connect",
    "I noticed your impressive",
    "Quick question",
    "circle back",
    "touch base",
    "low-hanging fruit",
    "synergies",
    "leverage our",
    "I am writing to",
]


@dataclass
class VoiceProfile:
    id: str
    owner_id: str
    channel: Channel
    tone: str                     # "direct" | "consultative" | "casual" | custom
    owner_name: str
    agency_name: str
    signature: str                # how the owner signs off
    sample_anchors: list[str] = field(default_factory=list)
    avoid_phrases: list[str] = field(default_factory=lambda: list(DEFAULT_AVOID))
    word_limit: int = 100         # tight by default; email goes to 150 in code


# Default sample anchors, generic but freight-broker-flavored. Owner replaces
# these with real past messages they liked.
DEFAULT_ANCHORS = {
    "linkedin": [
        "Saw the announcement on the new DC. Curious how you're thinking about outbound capacity for the ramp.",
        "Procurement review on the calendar yet? Happy to share what the 2026 carrier landscape is looking like.",
    ],
    "email": [
        "Subject: Your Memphis DC — outbound capacity\n\nNoticed the Q3 ribbon-cutting. Most operators we work with line up reefer capacity 90 days out for these — typically a 6–10% rate delta if you wait until go-live. Want a quick lay of the land for that lane?",
    ],
    "phone": [
        "Opening: 'Saw the news on the [signal]. Wanted to be the first call before procurement opens.'",
        "If pushback: 'I'm not here to bid. I'm here so you have a second opinion when you do.'",
    ],
}


class VoiceProfileRegistry:
    def __init__(self) -> None:
        self._profiles: dict[str, VoiceProfile] = {}
        self._seed()

    def _seed(self) -> None:
        # Seed one profile per channel for each demo owner.
        from ..prospects.source import prospect_source
        import asyncio
        try:
            owners = asyncio.get_event_loop().run_until_complete(prospect_source.owners()) \
                if False else None  # placeholder; we call sync via internal list
        except RuntimeError:
            owners = None

        # Pull synchronously from the stub source.
        owners = prospect_source._owners  # type: ignore[attr-defined]

        for owner in owners:
            for channel in ("linkedin", "email", "phone"):
                self.create(
                    owner_id=owner.id,
                    channel=channel,           # type: ignore[arg-type]
                    tone="direct",
                    owner_name=owner.name,
                    agency_name="the agency",
                    signature=f"— {owner.name.split()[0]}",
                    sample_anchors=list(DEFAULT_ANCHORS[channel]),
                )

    def create(self, *, owner_id: str, channel: Channel, tone: str, owner_name: str,
               agency_name: str, signature: str,
               sample_anchors: list[str] | None = None,
               avoid_phrases: list[str] | None = None,
               word_limit: int | None = None) -> VoiceProfile:
        profile = VoiceProfile(
            id=str(uuid4()),
            owner_id=owner_id, channel=channel, tone=tone,
            owner_name=owner_name, agency_name=agency_name,
            signature=signature,
            sample_anchors=sample_anchors or [],
            avoid_phrases=avoid_phrases if avoid_phrases is not None else list(DEFAULT_AVOID),
            word_limit=word_limit or (150 if channel == "email" else 100),
        )
        self._profiles[profile.id] = profile
        return profile

    def all(self) -> list[VoiceProfile]:
        return list(self._profiles.values())

    def for_owner(self, owner_id: str) -> list[VoiceProfile]:
        return [p for p in self._profiles.values() if p.owner_id == owner_id]

    def for_owner_channel(self, owner_id: str, channel: Channel) -> VoiceProfile | None:
        for p in self._profiles.values():
            if p.owner_id == owner_id and p.channel == channel:
                return p
        return None

    def update(self, profile_id: str, **fields) -> VoiceProfile | None:
        p = self._profiles.get(profile_id)
        if not p:
            return None
        for k, v in fields.items():
            if v is not None and hasattr(p, k):
                setattr(p, k, v)
        return p


registry = VoiceProfileRegistry()
