"""News + social feed."""
from fastapi import APIRouter, Query

router = APIRouter()


@router.get("")
async def list_events(
    source: str | None = Query(default=None),
    watchlist: str | None = Query(default=None),
    min_score: float = Query(default=0.0),
    limit: int = Query(default=50, le=200),
):
    """List events, newest first. Filterable by source/watchlist/score."""
    # TODO: real query
    return {"items": [], "filters": {"source": source, "watchlist": watchlist, "min_score": min_score}, "limit": limit}
