"""Cloud SQL async engine adapter (Task 4.1).

Builds the SQLAlchemy ``AsyncEngine`` through the Cloud SQL python connector
when ``settings.gcp_cloudsql_instance`` is armed. Uses the ``asyncpg`` driver
to match the existing async stack (the plain DSN engine is
``postgresql+asyncpg`` and relies on asyncpg ``server_settings`` for the
pool-exhaustion timeouts); the connector's ``connect_async`` forwards
driver kwargs to ``asyncpg.connect``, so ``server_settings`` ride through
unchanged. The connector is returned alongside the engine so the caller can
keep it alive for the engine's lifetime (the engine's ``async_creator``
closure also holds a reference).
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

_DbPool = Literal["primary", "background"]


def _Connector(loop: asyncio.AbstractEventLoop) -> Any:
    """Lazy construction of ``google.cloud.sql.connector.Connector``.

    Indirected so tests can monkeypatch the connector without importing the
    google package. The real default builds a Connector bound to ``loop``.
    """
    from google.cloud.sql.connector import Connector

    return Connector(loop=loop)


def _server_settings(settings: Any) -> dict[str, str]:
    """Mirror the plain-DSN engine's asyncpg server_settings (timeouts)."""
    pairs = (
        (
            "idle_in_transaction_session_timeout",
            settings.database_idle_in_transaction_timeout_ms,
        ),
        ("lock_timeout", settings.database_lock_timeout_ms),
    )
    return {key: str(value) for key, value in pairs if value > 0}


def async_engine_for_cloudsql(
    settings: Any, pool: _DbPool = "primary"
) -> tuple[AsyncEngine, Any]:
    """Build an async engine + connector for the configured Cloud SQL instance.

    Returns ``(engine, connector)``; the caller caches the connector next to
    the engine so it outlives the engine. ``async_creator`` closes over both.
    ``pool`` selects primary vs background sizing, mirroring the plain-DSN
    path in ``robofleet.db.base.get_engine`` so background loops stay on the
    smaller independent pool under Cloud SQL.
    """
    loop = asyncio.get_running_loop()
    connector = _Connector(loop)
    instance = settings.gcp_cloudsql_instance
    server_settings = _server_settings(settings)
    pool_size, max_overflow = (
        (settings.database_pool_size, settings.database_max_overflow)
        if pool == "primary"
        else (
            settings.database_background_pool_size,
            settings.database_background_max_overflow,
        )
    )

    async def getconn() -> Any:
        from google.cloud.sql.connector import IPTypes

        connect_kwargs: dict[str, Any] = {
            "user": settings.database_user,
            "password": settings.database_password,
            "db": settings.database_name,
            "ip_type": IPTypes.PRIVATE,
        }
        if server_settings:
            connect_kwargs["server_settings"] = server_settings
        return await connector.connect_async(instance, "asyncpg", **connect_kwargs)

    engine = create_async_engine(
        "postgresql+asyncpg://",
        async_creator=getconn,
        echo=settings.database_echo,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=settings.database_pool_timeout,
        pool_recycle=settings.database_pool_recycle,
        pool_pre_ping=True,
    )
    return engine, connector
