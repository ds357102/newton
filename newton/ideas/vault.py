"""Ideas vault — in-memory v0.1, Postgres v0.2."""
from __future__ import annotations
from datetime import datetime
from uuid import uuid4


class IdeasVault:
    def __init__(self):
        self._ideas: dict[str, dict] = {}

    def list(self, status: str | None = None) -> list[dict]:
        items = list(self._ideas.values())
        if status:
            items = [i for i in items if i["status"] == status]
        return sorted(items, key=lambda i: i["created_at"], reverse=True)

    def save(self, *, event_id: str | None = None, owner_note: str | None = None,
             tags: list[str] | None = None) -> dict:
        idea_id = str(uuid4())
        rec = {
            "id": idea_id, "event_id": event_id, "owner_note": owner_note,
            "tags": tags or [], "status": "raw", "drafts": [], "metrics": {},
            "created_at": datetime.utcnow().isoformat(),
        }
        self._ideas[idea_id] = rec
        return rec

    def get(self, idea_id: str) -> dict | None:
        return self._ideas.get(idea_id)

    def update(self, idea_id: str, **fields) -> dict | None:
        if idea_id not in self._ideas:
            return None
        self._ideas[idea_id].update(fields)
        return self._ideas[idea_id]


vault = IdeasVault()
