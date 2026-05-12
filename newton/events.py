"""Shared event envelope.

Every news/social hit, every KPI tick, every owner action becomes an Event.
This is the shape that the unified Alf+Elvva+Milburn+Newton platform will route on.
Keep it stable — additive changes only.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


SourceKind = Literal["reddit", "x", "linkedin", "rss", "web", "kpi", "manual"]


class Entity(BaseModel):
    """A named thing on a watchlist — company, person, hashtag, domain, query string."""
    id: UUID
    name: str
    kind: str  # "company" | "person" | "hashtag" | "domain" | "query"


class Event(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    source: SourceKind
    source_id: str | None = None
    ts_seen: datetime = Field(default_factory=datetime.utcnow)
    ts_published: datetime | None = None

    entities: list[Entity] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    score: float = 0.0          # 0..1 from relevance pass
    score_reason: str | None = None

    payload: dict[str, Any] = Field(default_factory=dict)
    # for news/social: title, url, excerpt, author, raw
    # for kpi:        symbol, value, delta, target

    def is_high_signal(self, threshold: float = 0.85) -> bool:
        return self.score >= threshold
