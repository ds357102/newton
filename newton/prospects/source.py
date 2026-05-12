"""ALF DB adapter for prospects.

Now per-account-owner. Each prospect has an owner_id; the source can return all
prospects, just one owner's, or just priority accounts. Stub data covers three
owners so the per-owner filter is exercisable end-to-end.

v0.4 swaps in a read-only async SQLAlchemy session against ALF's prospects table.
The shape returned here is the contract the rest of Newton consumes.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable


@dataclass
class Owner:
    id: str
    name: str
    email: str | None = None


@dataclass
class Prospect:
    id: str
    owner_id: str
    name: str
    priority: bool
    added_at: datetime
    last_touch_at: datetime | None
    dba_aliases: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    known_execs: list[str] = field(default_factory=list)
    facility_cities: list[str] = field(default_factory=list)
    industry: str | None = None
    archive_url_hashes: set[str] = field(default_factory=set)

    @property
    def days_on_list(self) -> int:
        return (datetime.utcnow() - self.added_at).days

    @property
    def is_cold_start(self) -> bool:
        return self.days_on_list < 30 and not self.archive_url_hashes

    def query_bundle(self) -> list[str]:
        terms = [self.name, *self.dba_aliases, *self.domains]
        for exec_name in self.known_execs:
            terms.append(f'"{exec_name}"')
        for city in self.facility_cities:
            terms.append(f'"{self.name}" "{city}"')
        return terms


class AlfProspectSource:
    """v0.3 stub. Three owners, mixed priority + cold-start prospects."""

    def __init__(self) -> None:
        now = datetime.utcnow()
        self._owners = [
            Owner(id="o_dan",   name="Dan Scherrer",  email="dan@example.com"),
            Owner(id="o_kim",   name="Kim Patel",     email="kim@example.com"),
            Owner(id="o_marco", name="Marco Reyes",   email="marco@example.com"),
        ]
        self._sample = [
            # --- Dan's book ---
            Prospect(
                id="p_001", owner_id="o_dan", name="Acme Logistics", priority=True,
                added_at=now - timedelta(days=210),
                last_touch_at=now - timedelta(days=12),
                dba_aliases=["Acme Co"], domains=["acmelogistics.com"],
                known_execs=["Karen Liu"], facility_cities=["Houston", "Dallas"],
                industry="3PL",
                archive_url_hashes={"deadbeef1"},
            ),
            Prospect(
                id="p_002", owner_id="o_dan", name="NorthStar Foods", priority=True,
                added_at=now - timedelta(days=5),  # cold start
                last_touch_at=None,
                dba_aliases=["NorthStar"], domains=["northstarfoods.com"],
                known_execs=["Sam Patel"], facility_cities=["Memphis"],
                industry="food manufacturing",
                archive_url_hashes=set(),
            ),
            Prospect(
                id="p_003", owner_id="o_dan", name="Harborline Manufacturing", priority=False,
                added_at=now - timedelta(days=120),
                last_touch_at=now - timedelta(days=60),
                dba_aliases=[], domains=["harborline.com"],
                known_execs=[], facility_cities=["Charleston"],
                industry="manufacturing",
                archive_url_hashes=set(),
            ),
            # --- Kim's book (intentionally quiet so recommendations kick in) ---
            Prospect(
                id="p_010", owner_id="o_kim", name="Lakeshore Beverage", priority=False,
                added_at=now - timedelta(days=300),
                last_touch_at=now - timedelta(days=180),
                domains=["lakeshorebev.com"], facility_cities=["Milwaukee"],
                industry="beverage manufacturing",
                archive_url_hashes={"old1", "old2"},  # everything's already in archive
            ),
            # --- Marco's book ---
            Prospect(
                id="p_020", owner_id="o_marco", name="Cascade Steel", priority=True,
                added_at=now - timedelta(days=60),
                last_touch_at=now - timedelta(days=30),
                domains=["cascadesteel.com"], facility_cities=["Portland"],
                industry="steel manufacturing",
                archive_url_hashes=set(),
            ),
            Prospect(
                id="p_021", owner_id="o_marco", name="Brightline Pharma", priority=False,
                added_at=now - timedelta(days=15),  # cold start
                last_touch_at=None,
                domains=["brightlinepharma.com"], facility_cities=["Raleigh"],
                industry="pharmaceutical manufacturing",
                archive_url_hashes=set(),
            ),
        ]

    async def owners(self) -> list[Owner]:
        return list(self._owners)

    async def all(self) -> list[Prospect]:
        return list(self._sample)

    async def for_owner(self, owner_id: str) -> list[Prospect]:
        return [p for p in self._sample if p.owner_id == owner_id]

    async def priority(self, owner_id: str | None = None) -> list[Prospect]:
        items = self._sample if owner_id is None else [p for p in self._sample if p.owner_id == owner_id]
        return [p for p in items if p.priority]

    async def get(self, prospect_id: str) -> Prospect | None:
        return next((p for p in self._sample if p.id == prospect_id), None)


prospect_source = AlfProspectSource()


# ---- v0.6: prospects override from JSON file ----
import json
import os
from pathlib import Path

PROSPECTS_FILE_ENV = "NEWTON_PROSPECTS_FILE"
DEFAULT_PROSPECTS_FILE = Path(__file__).resolve().parent.parent / "data" / "prospects.json"


def _load_override() -> tuple[list, list] | None:
    """If a prospects.json exists, parse and return (owners, prospects). Else None."""
    path = os.environ.get(PROSPECTS_FILE_ENV) or str(DEFAULT_PROSPECTS_FILE)
    try:
        with open(path) as f:
            data = json.load(f)
    except FileNotFoundError:
        return None
    except Exception as e:
        import logging
        logging.getLogger("newton.prospects.source").warning(f"failed to load {path}: {e}")
        return None

    owners = [Owner(**o) for o in data.get("owners", [])]
    prospects = []
    for raw in data.get("prospects", []):
        raw = dict(raw)
        for ts_field in ("added_at", "last_touch_at"):
            if raw.get(ts_field):
                raw[ts_field] = datetime.fromisoformat(raw[ts_field])
            elif ts_field in raw and raw[ts_field] is None:
                raw[ts_field] = None
        raw.setdefault("added_at", datetime.utcnow() - timedelta(days=60))
        if "archive_url_hashes" in raw and isinstance(raw["archive_url_hashes"], list):
            raw["archive_url_hashes"] = set(raw["archive_url_hashes"])
        prospects.append(Prospect(**raw))
    return owners, prospects


_override = _load_override()
if _override is not None:
    _override_owners, _override_prospects = _override
    prospect_source._owners = _override_owners
    prospect_source._sample = _override_prospects
    import logging
    logging.getLogger("newton.prospects.source").info(
        f"loaded prospects override: {len(_override_owners)} owners, {len(_override_prospects)} prospects"
    )
