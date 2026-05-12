"""Watchlists CRUD."""
from fastapi import APIRouter
from pydantic import BaseModel

from ..watchlists.registry import registry

router = APIRouter()


class WatchlistIn(BaseModel):
    name: str
    description: str | None = None
    entities: list[dict] = []
    alert_level: str = "feed"
    voice_tag: str | None = None
    cadence_seconds: int = 900


@router.get("")
async def list_watchlists():
    return registry.all()


@router.post("")
async def create_watchlist(wl: WatchlistIn):
    return registry.create(wl.model_dump())


@router.get("/{wl_id}")
async def get_watchlist(wl_id: str):
    return registry.get(wl_id)
