from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from waifu_bot.core.config import settings

engine: AsyncEngine | None = None
SessionLocal: sessionmaker | None = None


def init_engine() -> None:
    global engine, SessionLocal  # noqa: PLW0603
    if engine:
        return
    engine = create_async_engine(settings.postgres_dsn, echo=False, future=True)
    SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    if SessionLocal is None:
        init_engine()
    assert SessionLocal is not None  # for type checkers
    async with SessionLocal() as session:
        yield session

