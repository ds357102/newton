"""Dashboard endpoint — everything the Current Events UI needs in one call.

Single round-trip per owner switch:
  GET /current-events/{owner_id}
  → {owner, prospects[hits], recommendations, watchlists, stats}

The hits come from newton.store.hits (worker-updated cache). Recommendations
come from the recommendations engine. Watchlists from the in-memory registry.
"""
from fastapi import APIRouter, HTTPException

from ..prospects.source import prospect_source
from ..recommendations.engine import engine as reco_engine
from ..watchlists.registry import registry as wl_registry
from ..store import hits as hits_store

router = APIRouter()


def _serialize_prospect(p, prospect_hits):
    return {
        "id": p.id, "owner_id": p.owner_id, "name": p.name,
        "priority": p.priority, "industry": p.industry,
        "days_on_list": p.days_on_list,
        "is_cold_start": p.is_cold_start,
        "city": p.facility_cities[0] if p.facility_cities else None,
        "exec": p.known_execs[0] if p.known_execs else None,
        "hits": prospect_hits,
    }


@router.get("/{owner_id}")
async def get_dashboard(owner_id: str):
    owners = await prospect_source.owners()
    owner = next((o for o in owners if o.id == owner_id), None)
    if not owner:
        raise HTTPException(status_code=404, detail="owner not found")

    prospects = await prospect_source.for_owner(owner_id)
    hits_map = hits_store.for_owner(owner_id, [p.id for p in prospects])

    serialized = [_serialize_prospect(p, hits_map.get(p.id, [])) for p in prospects]

    recos = await reco_engine.for_owner(owner_id, limit=6)

    return {
        "owner": {"id": owner.id, "name": owner.name, "email": owner.email},
        "prospects": serialized,
        "stats": {
            "total": len(serialized),
            "priority": sum(1 for p in serialized if p["priority"]),
            "cold_start": sum(1 for p in serialized if p["is_cold_start"]),
            "hits": sum(len(p["hits"]) for p in serialized),
        },
        "recommendations": [
            {
                "company_name": r.company_name, "industry": r.industry,
                "signal_category": r.signal_category, "headline": r.headline,
                "excerpt": r.excerpt, "source_url": r.source_url,
                "age_days": r.age_days, "score": r.score, "rationale": r.rationale,
            } for r in recos
        ],
        "watchlists": [
            {"id": w["id"], "name": w["name"],
             "alert_level": w.get("alert_level"),
             "entity_count": len(w.get("entities", []))}
            for w in wl_registry.all()
        ],
    }


@router.get("")
async def list_owners_compact():
    """Convenience: list owners for the UI's dropdown."""
    items = await prospect_source.owners()
    return {"items": [{"id": o.id, "name": o.name} for o in items]}
