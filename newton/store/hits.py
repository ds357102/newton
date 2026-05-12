"""Hit cache.

Maps prospect_id → list of currently-surfaced hits (from the monitor pipeline).
v0.6: in-memory, seeded from newton/data/seed_hits.json so the UI shows
something on first load. The worker (workers/run_monitor.py) updates the cache
when it runs; in a future milestone this gets replaced with a Postgres-backed
events table queried with proper filters.
"""
from __future__ import annotations
import json
import logging
import os
from pathlib import Path

log = logging.getLogger("newton.store.hits")

# {prospect_id: [hit_dict, ...]}
_HITS: dict[str, list[dict]] = {}

SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "seed_hits.json"


def _load_seed() -> None:
    global _HITS
    seed_file = os.environ.get("NEWTON_HITS_FILE") or str(SEED_PATH)
    try:
        with open(seed_file) as f:
            data = json.load(f)
        _HITS = data
        log.info(f"hit cache loaded from {seed_file}: {sum(len(v) for v in data.values())} hits across {len(data)} prospects")
    except FileNotFoundError:
        log.info(f"no hit seed at {seed_file}; hit cache starts empty")
    except Exception as e:
        log.warning(f"failed to load hit seed {seed_file}: {e}")


def for_prospect(prospect_id: str) -> list[dict]:
    return list(_HITS.get(prospect_id, []))


def for_owner(owner_id: str, prospect_ids: list[str]) -> dict[str, list[dict]]:
    return {pid: for_prospect(pid) for pid in prospect_ids}


def set_for_prospect(prospect_id: str, hits: list[dict]) -> None:
    _HITS[prospect_id] = hits
    _persist()


def replace_all(hits_by_prospect: dict[str, list[dict]]) -> None:
    """Used by the worker after a run."""
    global _HITS
    _HITS = dict(hits_by_prospect)
    _persist()


def clear() -> None:
    _HITS.clear()


def total_count() -> int:
    return sum(len(v) for v in _HITS.values())


_load_seed()

# ---- v0.6: optional disk persistence ----
def _persist() -> None:
    """Write the current cache to NEWTON_HITS_FILE so it survives restarts.
    Called automatically by set_for_prospect / replace_all when the env var
    NEWTON_PERSIST_HITS is truthy. The streamer worker handles its own writes."""
    if not os.environ.get("NEWTON_PERSIST_HITS"):
        return
    target = os.environ.get("NEWTON_HITS_FILE") or str(SEED_PATH)
    try:
        tmp = target + ".tmp"
        with open(tmp, "w") as f:
            json.dump(_HITS, f, indent=2, default=str)
        os.replace(tmp, target)
    except Exception as e:
        log.warning(f"hit cache persist failed: {e}")
