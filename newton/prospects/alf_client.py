"""ALF API client.

Calls ALF's `/api/prospects` (and optionally `/api/clients`) over HTTPS with a
bearer token. Returns raw JSON; the prospect source maps to Newton's Prospect
dataclass with defensive field handling (since ALF's schema may add/rename
fields independently of Newton).

Designed to fail soft: if ALF is unreachable, the client returns None and the
caller falls back to whatever it had cached. Newton never crashes because ALF
is offline.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Any

import httpx

from ..config import settings

log = logging.getLogger("newton.alf")

TIMEOUT = 20


class AlfApiClient:
    def __init__(self, base_url: str | None = None, token: str | None = None) -> None:
        self.prospects_url = base_url or settings.alf_api_url
        self.clients_url = settings.alf_clients_url
        self.token = token or settings.newton_api_token

    def is_configured(self) -> bool:
        return bool(self.prospects_url and self.token)

    async def _fetch(self, url: str) -> list[dict] | None:
        if not self.token:
            log.warning("ALF token not set; skipping fetch")
            return None
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "User-Agent": "newton/0.6 (+web)",
        }
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
                r = await client.get(url, headers=headers)
                r.raise_for_status()
                data = r.json()
        except httpx.HTTPStatusError as e:
            log.warning(f"ALF GET {url} failed: HTTP {e.response.status_code} — body preview: {e.response.text[:200]!r}")
            return None
        except Exception as e:
            log.warning(f"ALF GET {url} failed: {e}")
            return None

        # Be liberal with response shape. Accept a bare list, or a wrapped
        # object with a list under one of these common keys.
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("records", "items", "prospects", "clients", "data", "results", "accounts"):
                if key in data and isinstance(data[key], list):
                    return data[key]
            # Last-resort fallback: take the first list-valued key.
            for key, val in data.items():
                if isinstance(val, list) and val and isinstance(val[0], dict):
                    log.info(f"ALF response: using fallback key {key!r} with {len(val)} records")
                    return val
        log.warning(f"ALF response shape unexpected at {url}: top-level keys = {list(data)[:6] if isinstance(data, dict) else type(data).__name__}")
        return None

    async def fetch_prospects(self) -> list[dict] | None:
        if not self.prospects_url:
            return None
        return await self._fetch(self.prospects_url)

    async def fetch_clients(self) -> list[dict] | None:
        if not self.clients_url:
            return None
        return await self._fetch(self.clients_url)

    async def fetch_all(self) -> list[dict] | None:
        """Merge prospects + clients (if separate endpoints). Adds 'status': 'client'
        to records from the clients endpoint when ALF doesn't tag them."""
        results: list[dict] = []

        prospects = await self.fetch_prospects()
        if prospects:
            results.extend(prospects)

        if self.clients_url:
            clients = await self.fetch_clients()
            if clients:
                for c in clients:
                    if not c.get("status"):
                        c["status"] = "client"
                results.extend(clients)

        return results or None


client = AlfApiClient()
