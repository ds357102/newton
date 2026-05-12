"""Async SQLAlchemy engine + session factory."""
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession

from .config import settings

engine = create_async_engine(settings.database_url, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncSession:
    async with SessionLocal() as s:
        yield s
