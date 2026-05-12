"""KPI adapter interface. Real adapters (TMS, accounting) plug in here."""
from abc import ABC, abstractmethod
from typing import Any


class KPIAdapter(ABC):
    @abstractmethod
    async def fetch_all(self) -> dict[str, dict[str, Any]]:
        """Return {symbol: {sym, val, delta, dir, target?}}."""
        ...
