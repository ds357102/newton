"""ALF notes integration.

v0.6: stub. Calls to send_note() enqueue into an in-memory queue and log,
so the UI's "→ ALF notes" button works end-to-end without ALF being live.
v1.0: real client calls ALF's POST /notes endpoint when integration lands.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
import logging
from uuid import uuid4

log = logging.getLogger("newton.integrations.alf")


@dataclass
class PendingNote:
    id: str
    prospect_id: str
    owner_id: str
    event_id: str | None
    title: str
    body: str
    source_url: str | None
    queued_at: datetime
    sent_at: datetime | None = None
    status: str = "pending"        # pending | sent | failed
    metadata: dict = field(default_factory=dict)


class AlfStubClient:
    """In-memory queue. drain_to_alf() is a no-op until v1.0 wires real API."""

    def __init__(self) -> None:
        self._queue: list[PendingNote] = []

    def send_note(self, *, prospect_id: str, owner_id: str, title: str, body: str,
                  event_id: str | None = None, source_url: str | None = None,
                  metadata: dict | None = None) -> PendingNote:
        note = PendingNote(
            id=str(uuid4()),
            prospect_id=prospect_id, owner_id=owner_id, event_id=event_id,
            title=title, body=body, source_url=source_url,
            queued_at=datetime.utcnow(),
            metadata=metadata or {},
        )
        self._queue.append(note)
        log.info(f"queued ALF note {note.id} for prospect {prospect_id} ({title[:50]!r})")
        return note

    def pending(self, owner_id: str | None = None) -> list[PendingNote]:
        items = self._queue
        if owner_id:
            items = [n for n in items if n.owner_id == owner_id]
        return [n for n in items if n.status == "pending"]

    def drain_to_alf(self) -> int:
        """v1.0: POST each pending note to ALF. Returns count sent. v0.6: noop."""
        # TODO at integration: httpx POST /alf/api/notes for each pending
        return 0


client = AlfStubClient()
