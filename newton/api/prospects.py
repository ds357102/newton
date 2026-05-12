"""Prospects API — Newton's anchor route. Per-account-owner.

When Newton folds into ALF, this gets re-mounted under /current-events/prospects.
"""
from fastapi import APIRouter, HTTPException, Query

from ..prospects.source import prospect_source

router = APIRouter()


@router.get("/owners")
async def list_owners():
    return {"items": [{"id": o.id, "name": o.name, "email": o.email}
                      for o in await prospect_source.owners()]}


@router.get("")
async def list_prospects(
    owner_id: str | None = Query(default=None),
    priority_only: bool = Query(default=False),
):
    if owner_id:
        items = await prospect_source.for_owner(owner_id)
    else:
        items = await prospect_source.all()
    if priority_only:
        items = [p for p in items if p.priority]
    return {
        "items": [
            {
                "id": p.id, "owner_id": p.owner_id,
                "name": p.name, "priority": p.priority,
                "industry": p.industry,
                "added_at": p.added_at.isoformat(),
                "last_touch_at": p.last_touch_at.isoformat() if p.last_touch_at else None,
                "days_on_list": p.days_on_list,
                "is_cold_start": p.is_cold_start,
                "facility_cities": p.facility_cities,
                "known_execs": p.known_execs,
            } for p in items
        ]
    }


@router.get("/{prospect_id}")
async def get_prospect(prospect_id: str):
    p = await prospect_source.get(prospect_id)
    if not p:
        raise HTTPException(status_code=404, detail="prospect not found")
    return {
        "id": p.id, "owner_id": p.owner_id,
        "name": p.name, "priority": p.priority,
        "industry": p.industry,
        "added_at": p.added_at.isoformat(),
        "last_touch_at": p.last_touch_at.isoformat() if p.last_touch_at else None,
        "days_on_list": p.days_on_list,
        "is_cold_start": p.is_cold_start,
        "query_bundle": p.query_bundle(),
        "facility_cities": p.facility_cities,
        "known_execs": p.known_execs,
    }

# ---- v0.6: outreach drafting ----
from pydantic import BaseModel
from ..ideas.drafting import draft_outreach


class DraftRequest(BaseModel):
    channel: str = "linkedin"
    signal: dict
    """The buying signal context. Shape: {title, excerpt, signal_category, reason, key_phrases}"""


@router.post("/{prospect_id}/draft-outreach")
async def post_draft_outreach(prospect_id: str, body: DraftRequest):
    p = await prospect_source.get(prospect_id)
    if not p:
        raise HTTPException(status_code=404, detail="prospect not found")
    prospect_payload = {
        "id": p.id, "owner_id": p.owner_id, "name": p.name,
        "industry": p.industry, "priority": p.priority,
        "is_cold_start": p.is_cold_start, "days_on_list": p.days_on_list,
    }
    return await draft_outreach(
        prospect=prospect_payload,
        signal=body.signal,
        channel=body.channel,
        owner_id=p.owner_id,
    )
