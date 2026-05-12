"""Automation tier configuration per workflow."""
from fastapi import APIRouter
from ..automation.tiers import tiers

router = APIRouter()


@router.get("")
async def list_tiers():
    return tiers.all()


@router.post("/{workflow}/{tier}")
async def set_tier(workflow: str, tier: int):
    return tiers.set(workflow, tier)
