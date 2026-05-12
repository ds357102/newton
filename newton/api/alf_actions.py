"""ALF action endpoints — outbound to ALF (notes today, more at integration).

Stub queue today; real ALF API call at v1.0.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from ..integrations.alf import client as alf_client

router = APIRouter()


class NoteIn(BaseModel):
    prospect_id: str
    owner_id: str
    title: str
    body: str
    event_id: str | None = None
    source_url: str | None = None
    metadata: dict | None = None


@router.post("/notes")
async def send_note(note: NoteIn):
    n = alf_client.send_note(**note.model_dump(exclude_none=True))
    return {
        "id": n.id, "prospect_id": n.prospect_id, "owner_id": n.owner_id,
        "status": n.status, "queued_at": n.queued_at.isoformat(),
        "title": n.title, "source_url": n.source_url,
    }


@router.get("/notes/pending")
async def pending(owner_id: str | None = None):
    items = alf_client.pending(owner_id=owner_id)
    return {"items": [
        {"id": n.id, "prospect_id": n.prospect_id, "owner_id": n.owner_id,
         "title": n.title, "body": n.body, "source_url": n.source_url,
         "queued_at": n.queued_at.isoformat(), "status": n.status}
        for n in items
    ]}
