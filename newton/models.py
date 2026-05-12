"""ORM models. Mirrors events.py shape; alembic migrations are TODO."""
from datetime import datetime
from sqlalchemy import String, Float, JSON, DateTime, ForeignKey, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class EventRow(Base):
    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String(16), index=True)
    source_id: Mapped[str | None] = mapped_column(String, nullable=True)
    ts_seen: Mapped[datetime] = mapped_column(DateTime, index=True)
    ts_published: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    score_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class Watchlist(Base):
    __tablename__ = "watchlists"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    alert_level: Mapped[str] = mapped_column(String, default="feed")  # feed|push|sms
    voice_tag: Mapped[str | None] = mapped_column(String, nullable=True)
    cadence_seconds: Mapped[int] = mapped_column(Integer, default=900)
    entities: Mapped[list] = mapped_column(JSON, default=list)


class Idea(Base):
    __tablename__ = "ideas"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    event_id: Mapped[str | None] = mapped_column(String, ForeignKey("events.id"), nullable=True)
    owner_note: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="raw")  # raw|sketched|drafted|scheduled|published|archived
    tags: Mapped[list] = mapped_column(JSON, default=list)
    drafts: Mapped[list] = mapped_column(JSON, default=list)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
