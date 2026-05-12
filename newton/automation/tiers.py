"""Per-workflow automation tier (0..4). Owner picks how far each can climb.
from __future__ import annotations

  0  surface only
  1  surface + nudge
  2  auto-draft, owner reviews
  3  schedule, owner approves
  4  hands-off (narrow scope)
"""
DEFAULT_TIERS = {
    "ingest": 1,
    "draft": 2,
    "schedule": 0,
    "publish": 0,
    "reshare": 0,
}


class Tiers:
    def __init__(self):
        self._t = dict(DEFAULT_TIERS)

    def all(self) -> dict[str, int]:
        return dict(self._t)

    def set(self, workflow: str, tier: int) -> dict[str, int]:
        if not 0 <= tier <= 4:
            raise ValueError("tier must be 0..4")
        self._t[workflow] = tier
        return self.all()


tiers = Tiers()
