"""Ideas vault."""
from fastapi import APIRouter
from pydantic import BaseModel

from ..ideas.vault import vault

router = APIRouter()


class IdeaIn(BaseModel):
    event_id: str | None = None
    owner_note: str | None = None
    tags: list[str] = []


@router.get("")
async def list_ideas(status: str | None = None):
    return vault.list(status=status)


@router.post("")
async def save_idea(idea: IdeaIn):
    return vault.save(**idea.model_dump())


@router.post("/{idea_id}/draft")
async def draft(idea_id: str, channel: str = "linkedin"):
    """Generate a draft for this idea via the LLM. Tier-2 automation."""
    from ..ideas.drafting import draft_for_idea
    return await draft_for_idea(idea_id, channel=channel)
