"""Dashboard endpoint — everything the Current Events UI needs in one call.

Single round-trip per owner switch:
  GET /current-events/{owner_id}
  → {owner, prospects[hits], recommendations, watchlists, stats}

The hits come from newton.store.hits (worker-updated cache). Recommendations
come from the recommendations engine. Watchlists from the in-memory registry.
"""
from fastapi import APIRouter, HTTPException, Query

from ..prospects.source import prospect_source
from ..recommendations.engine import engine as reco_engine
from ..watchlists.registry import registry as wl_registry
from ..store import hits as hits_store

router = APIRouter()

# Cap how many prospects we serialize into one dashboard response. With 3,889
# accounts and a single owner having hundreds, we still want fast page loads.
# Prospects without hits get truncated past this number (priority/cold-start
# always come back regardless).
MAX_PROSPECTS_IN_RESPONSE = 200


def _serialize_prospect(p, prospect_hits):
    return {
        "id": p.id, "owner_id": p.owner_id, "name": p.name,
        "priority": p.priority, "industry": p.industry,
        "status": p.status,
        "days_on_list": p.days_on_list,
        "is_cold_start": p.is_cold_start,
        "city": p.facility_cities[0] if p.facility_cities else None,
        "exec": p.known_execs[0] if p.known_execs else None,
        "hits": prospect_hits,
    }


@router.get("/{owner_id}")
async def get_dashboard(
    owner_id: str,
    status: str | None = Query(default=None, description="Filter by status: open / client / closed_won / closed_lost"),
):
    owners = await prospect_source.owners()
    owner = next((o for o in owners if o.id == owner_id), None)
    if not owner:
        raise HTTPException(status_code=404, detail="owner not found")

    prospects = await prospect_source.by_status(owner_id, status)
    hits_map = hits_store.for_owner(owner_id, [p.id for p in prospects])

    # Sort: priority first, then cold-start, then hits-having, then everything else
    def _sort_key(p):
        has_hits = bool(hits_map.get(p.id))
        return (
            0 if p.priority else 1,
            0 if p.is_cold_start else 1,
            0 if has_hits else 1,
            p.name.lower(),
        )
    prospects_sorted = sorted(prospects, key=_sort_key)

    # Always include priority + cold-start + hits-having; cap the rest
    full = [p for p in prospects_sorted if p.priority or p.is_cold_start or hits_map.get(p.id)]
    rest = [p for p in prospects_sorted if p not in full]
    visible = full + rest[:max(0, MAX_PROSPECTS_IN_RESPONSE - len(full))]

    serialized = [_serialize_prospect(p, hits_map.get(p.id, [])) for p in visible]
    recos = await reco_engine.for_owner(owner_id, limit=6)

    return {
        "owner": {"id": owner.id, "name": owner.name, "email": owner.email},
        "prospects": serialized,
        "stats": {
            "total": len(prospects),
            "shown": len(serialized),
            "priority": sum(1 for p in prospects if p.priority),
            "cold_start": sum(1 for p in prospects if p.is_cold_start),
            "hits": sum(len(h) for h in hits_map.values()),
        },
        "filters": {"status": status},
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
