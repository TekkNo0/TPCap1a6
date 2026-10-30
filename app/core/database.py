from collections.abc import AsyncGenerator
from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings


def create_db_engine(settings: Settings) -> AsyncEngine:
    """Crea el motor asincrónico de SQLAlchemy con pool configurado.

    Debe llamarse exclusivamente durante el lifespan de la aplicación.
    """
    return create_async_engine(
        settings.database_url,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        echo=settings.SQL_ECHO,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Crea la fábrica de sesiones asincrónicas con expire_on_commit=False.

    Debe llamarse durante el lifespan y almacenarse en app.state.session_factory.
    """
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Dependencia FastAPI que provee una sesión de BD por petición.

    Toma la fábrica de sesiones desde request.app.state.session_factory,
    crea la sesión y asegura su cierre al finalizar la petición HTTP.
    """
    session_factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with session_factory() as session:
        yield session
