"""Voice profile API. Owner manages per-channel tone + samples + avoid-phrases."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..voice.profiles import registry, Channel

router = APIRouter()


class VoiceProfileIn(BaseModel):
    owner_id: str
    channel: Channel
    tone: str = "direct"
    owner_name: str
    agency_name: str = "the agency"
    signature: str = "—"
    sample_anchors: list[str] = []
    avoid_phrases: list[str] | None = None
    word_limit: int | None = None


class VoiceProfilePatch(BaseModel):
    tone: str | None = None
    owner_name: str | None = None
    agency_name: str | None = None
    signature: str | None = None
    sample_anchors: list[str] | None = None
    avoid_phrases: list[str] | None = None
    word_limit: int | None = None


def _serialize(p):
    return {
        "id": p.id, "owner_id": p.owner_id, "channel": p.channel, "tone": p.tone,
        "owner_name": p.owner_name, "agency_name": p.agency_name,
        "signature": p.signature, "sample_anchors": p.sample_anchors,
        "avoid_phrases": p.avoid_phrases, "word_limit": p.word_limit,
    }


@router.get("/profiles")
async def list_profiles(owner_id: str | None = None):
    items = registry.for_owner(owner_id) if owner_id else registry.all()
    return {"items": [_serialize(p) for p in items]}


@router.post("/profiles")
async def create_profile(body: VoiceProfileIn):
    p = registry.create(**body.model_dump(exclude_none=True))
    return _serialize(p)


@router.patch("/profiles/{profile_id}")
async def update_profile(profile_id: str, body: VoiceProfilePatch):
    p = registry.update(profile_id, **body.model_dump(exclude_unset=True))
    if not p:
        raise HTTPException(status_code=404, detail="profile not found")
    return _serialize(p)
