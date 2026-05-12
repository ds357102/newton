"""In-memory watchlist registry (v0.3). Backed by Postgres in a later milestone."""
from __future__ import annotations
from uuid import uuid4


class WatchlistRegistry:
    def __init__(self):
        self._wl: dict[str, dict] = {}
        self._seed()

    def _seed(self):
        # v0.3 seed — see Newton_Spec.docx §6
        for wl in [
            {"name": "Expos & trade shows", "alert_level": "feed", "voice_tag": "industry-signal",
             "cadence_seconds": 3600,
             "entities": [
                 {"name": "MATS", "kind": "query"},
                 {"name": "Manifest", "kind": "query"},
                 {"name": "FreightWaves Future of Supply Chain", "kind": "query"},
             ]},
            {"name": "Client news", "alert_level": "push", "voice_tag": "client-care",
             "cadence_seconds": 900,
             "entities": []},  # populated from ALF client list
            {"name": "Prospect news", "alert_level": "push", "voice_tag": "owner-direct",
             "cadence_seconds": 300,
             "entities": []},  # populated from ALF prospect list
            {"name": "Industry news", "alert_level": "feed", "voice_tag": "industry-signal",
             "cadence_seconds": 3600,
             "entities": [
                 {"name": "logistics", "kind": "query"},
                 {"name": "freight", "kind": "query"},
                 {"name": "supply chain", "kind": "query"},
             ]},
            {"name": "Event news", "alert_level": "feed", "voice_tag": "industry-signal",
             "cadence_seconds": 86400,
             "entities": []},
            {"name": "Economic", "alert_level": "feed", "voice_tag": "macro-signal",
             "cadence_seconds": 86400,
             "entities": [
                 {"name": "CPI", "kind": "query"},
                 {"name": "PPI", "kind": "query"},
                 {"name": "manufacturing PMI", "kind": "query"},
                 {"name": "retail sales", "kind": "query"},
             ]},
            {"name": "Transport", "alert_level": "feed", "voice_tag": "industry-signal",
             "cadence_seconds": 3600,
             "entities": [
                 {"name": "FMCSA", "kind": "query"},
                 {"name": "DOT", "kind": "query"},
                 {"name": "carrier earnings", "kind": "query"},
                 {"name": "port volumes", "kind": "query"},
             ]},
        ]:
            self.create(wl)

    def all(self) -> list[dict]:
        return list(self._wl.values())

    def get(self, wl_id: str) -> dict | None:
        return self._wl.get(wl_id)

    def create(self, data: dict) -> dict:
        wl_id = str(uuid4())
        rec = {"id": wl_id, "alert_level": "feed", "cadence_seconds": 900, **data}
        self._wl[wl_id] = rec
        return rec


registry = WatchlistRegistry()
