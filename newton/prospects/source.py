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
    status: str = "open"  # open | client | closed_won | closed_lost | other
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

    async def by_status(self, owner_id: str | None, status: str | None) -> list[Prospect]:
        items = self._sample if owner_id is None else [p for p in self._sample if p.owner_id == owner_id]
        if status:
            items = [p for p in items if (p.status or "open").lower() == status.lower()]
        return items

    # ---- v0.7: live sync from ALF's /api/prospects ----
    async def refresh_from_alf(self) -> int:
        """Pull fresh prospect data from ALF and replace the in-memory cache.

        Returns the number of prospects loaded. Returns 0 (and keeps existing
        data) if ALF is not configured or unreachable.
        """
        import logging
        log = logging.getLogger("newton.prospects.source")
        try:
            from .alf_client import client as alf
        except Exception as e:
            log.warning(f"ALF client import failed: {e}")
            return 0
        if not alf.is_configured():
            return 0

        raw = await alf.fetch_all()
        if not raw:
            log.info("ALF fetch returned no data; keeping existing cache")
            return 0

        owners_by_id: dict[str, Owner] = {}
        prospects: list[Prospect] = []
        skipped_junk = 0
        for r in raw:
            if not isinstance(r, dict):
                continue
            pid = str(r.get("id") or r.get("_id") or r.get("uuid") or "").strip()
            if not pid:
                continue
            # Junk filter: ALF's response contains placeholder records where
            # name == id (no real company name was ever entered). Skip them so
            # they don't pollute counts or owner lists.
            raw_name = r.get("name") or r.get("company_name") or r.get("account_name")
            if not raw_name or str(raw_name).strip() == pid:
                skipped_junk += 1
                continue
            # ALF returns owner_id: null for genuinely unassigned accounts.
            # Distinguish "unassigned" from "missing field" so the UI shows a
            # clean "Unassigned" bucket instead of an opaque "o_unknown".
            raw_owner = (
                r.get("owner_id") if "owner_id" in r else
                r.get("ownerId") or r.get("assigned_to") or r.get("assignedTo") or
                r.get("rep_id") or r.get("owner")
            )
            if not raw_owner:
                owner_id = "unassigned"
                owner_name = "Unassigned"
            else:
                owner_id = str(raw_owner)
                owner_name = (
                    r.get("owner_name") or r.get("ownerName") or
                    r.get("assignee_name") or r.get("rep_name") or owner_id
                )
            if owner_id not in owners_by_id:
                owners_by_id[owner_id] = Owner(
                    id=owner_id, name=owner_name,
                    email=r.get("owner_email") or r.get("ownerEmail"),
                )
            added_at = _parse_ts(r.get("added_at") or r.get("addedAt") or r.get("created_at") or r.get("createdAt"))
            last_touch_at = _parse_ts(
                r.get("last_touch_at") or r.get("lastTouchAt") or
                r.get("last_contact") or r.get("lastContact") or r.get("last_activity_at")
            )
            # Status: prefer explicit `status` field; fall back to `is_open` bool.
            status_raw = r.get("status")
            if status_raw is None:
                status_raw = "open" if (r.get("is_open") or r.get("isOpen")) else "open"
            status = str(status_raw).lower().strip()
            priority = bool(
                r.get("priority") or r.get("is_priority") or r.get("isPriority") or
                status == "priority"
            )
            # Domains / cities / execs may be string or list
            def _aslist(v):
                if not v: return []
                return v if isinstance(v, list) else [str(v)]
            domains = _aslist(r.get("domain")) + _aslist(r.get("domains"))
            cities = _aslist(r.get("city")) + _aslist(r.get("facility_cities")) + _aslist(r.get("cities"))
            execs  = _aslist(r.get("key_exec")) + _aslist(r.get("known_execs")) + _aslist(r.get("execs"))

            prospects.append(Prospect(
                id=pid,
                owner_id=owner_id,
                name=str(r.get("name") or r.get("company_name") or r.get("account_name") or pid),
                priority=priority,
                added_at=added_at or (datetime.utcnow() - timedelta(days=30)),
                last_touch_at=last_touch_at,
                dba_aliases=_aslist(r.get("dba_aliases") or r.get("aliases")),
                domains=list(dict.fromkeys([d for d in domains if d])),
                known_execs=list(dict.fromkeys([e for e in execs if e])),
                facility_cities=list(dict.fromkeys([c for c in cities if c])),
                industry=r.get("industry"),
                status=status,
            ))

        if not prospects:
            log.warning("ALF returned data but no parseable prospect records; cache unchanged")
            return 0

        self._owners = list(owners_by_id.values())
        self._sample = prospects
        log.info(
            f"ALF sync OK: {len(prospects)} prospects across {len(self._owners)} owners"
            + (f" (skipped {skipped_junk} junk records where name == id)" if skipped_junk else "")
        )
        return len(prospects)


def _parse_ts(val) -> datetime | None:
    if not val: return None
    if isinstance(val, datetime): return val
    try:
        return datetime.fromisoformat(str(val).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


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
