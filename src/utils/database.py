"""
Couche d'accès aux bases de données.

Gère les connexions PostgreSQL/TimescaleDB et Redis.
Session factory avec async support.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import config
from src.utils.logging import get_logger

logger = get_logger(__name__)


class DatabaseManager:
    """
    Gestionnaire de connexions aux bases de données.

    Gère le cycle de vie des connexions PostgreSQL/TimescaleDB et Redis.
    """

    def __init__(self) -> None:
        self._pg_engine = None
        self._async_session_maker: async_sessionmaker[AsyncSession] | None = None
        self._redis: aioredis.Redis | None = None
        self._pg_pool: asyncpg.Pool | None = None

    # ─── PostgreSQL / TimescaleDB ─────────────────────────────

    async def init_postgres(self) -> None:
        """Initialise la connexion PostgreSQL avec SQLAlchemy async."""
        if self._pg_engine is not None:
            return

        self._pg_engine = create_async_engine(
            config.database_url,
            pool_size=20,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=False,
        )

        self._async_session_maker = async_sessionmaker(
            self._pg_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        self._pg_pool = await asyncpg.create_pool(
            config.database_url.replace("postgresql+asyncpg://", "postgresql://"),
            min_size=5,
            max_size=20,
        )

        logger.info("Connexion PostgreSQL initialisée")

    async def close_postgres(self) -> None:
        """Ferme la connexion PostgreSQL."""
        if self._pg_pool:
            await self._pg_pool.close()
        if self._pg_engine:
            await self._pg_engine.dispose()
        logger.info("Connexion PostgreSQL fermée")

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Fournit une session SQLAlchemy async (context manager)."""
        if self._async_session_maker is None:
            raise RuntimeError("PostgreSQL non initialisé.")

        async with self._async_session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def execute_raw(self, query: str, *args: Any) -> Any:
        """Exécute une requête SQL directe via asyncpg."""
        if self._pg_pool is None:
            raise RuntimeError("PostgreSQL pool non initialisé.")
        async with self._pg_pool.acquire() as conn:
            return await conn.fetch(query, *args)

    # ─── Redis ────────────────────────────────────────────────

    async def init_redis(self) -> None:
        """Initialise la connexion Redis."""
        if self._redis is not None:
            return

        self._redis = aioredis.from_url(
            config.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
            health_check_interval=30,
        )

        await self._redis.ping()
        logger.info("Connexion Redis initialisée")

    async def close_redis(self) -> None:
        """Ferme la connexion Redis."""
        if self._redis:
            await self._redis.close()
        logger.info("Connexion Redis fermée")

    @property
    def redis(self) -> aioredis.Redis:
        """Retourne le client Redis."""
        if self._redis is None:
            raise RuntimeError("Redis non initialisé.")
        return self._redis

    @property
    def pg_pool(self) -> asyncpg.Pool:
        """Retourne le pool asyncpg."""
        if self._pg_pool is None:
            raise RuntimeError("PostgreSQL pool non initialisé.")
        return self._pg_pool

    # ─── Cycle de vie global ──────────────────────────────────

    async def initialize(self) -> None:
        """Initialise toutes les connexions DB."""
        await self.init_postgres()
        await self.init_redis()
        logger.info("Toutes les connexions DB initialisées")

    async def shutdown(self) -> None:
        """Ferme toutes les connexions DB proprement."""
        await self.close_postgres()
        await self.close_redis()
        logger.info("Toutes les connexions DB fermées")


db = DatabaseManager()
