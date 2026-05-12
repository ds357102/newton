"""Mock KPI adapter — emits plausible numbers so the ticker is alive on day one."""
import random
from typing import Any

from .base import KPIAdapter


SYMBOLS = [
    ("REV",   "$2.41M", 1.8,  "up"),
    ("GP",    "$487K",  0.6,  "up"),
    ("LOADS", "1,284",  12,   "up"),
    ("MARGIN","20.2%", -0.3,  "down"),
    ("DSO",   "38d",   -1,    "up"),
    ("LANES", "312",    4,    "up"),
    ("DEALS", "21",     3,    "up"),
    ("NPS",   "68",     2,    "up"),
    ("PIPE",  "$5.9M",  0.4,  "up"),
    ("HEAD",  "14",     0,    "flat"),
]


class MockKPIAdapter(KPIAdapter):
    async def fetch_all(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for sym, val, delta, dir_ in SYMBOLS:
            out[sym] = {"sym": sym, "val": val, "delta": delta, "dir": dir_}
        return out

    async def jitter(self) -> dict[str, Any]:
        sym, val, delta, dir_ = random.choice(SYMBOLS)
        return {"sym": sym, "val": val, "delta": round(delta + random.uniform(-0.2, 0.2), 2), "dir": dir_}
