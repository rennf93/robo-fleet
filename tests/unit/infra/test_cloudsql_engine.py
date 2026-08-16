"""Cloud SQL async engine adapter (Task 4.1).

When ``gcp_cloudsql_instance`` is armed, ``get_engine`` builds the async engine
through the Cloud SQL python connector (``async_creator`` over asyncpg) instead
of the plain DSN. When it is empty, the existing path is unchanged.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from robofleet.config import Settings
from robofleet.db import base as db_base
from robofleet.infra import cloudsql


@pytest.fixture
def _holder_reset(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Isolate _DbHolder so the test never touches the real engine."""
    monkeypatch.setattr(db_base._DbHolder, "engine", None)
    monkeypatch.setattr(db_base._DbHolder, "session_factory", None)
    monkeypatch.setattr(db_base._DbHolder, "loop", None)
    monkeypatch.setattr(db_base._DbHolder, "cloudsql_connector", None)
    return db_base._DbHolder


async def test_cloudsql_engine_uses_connector_when_instance_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """async_engine_for_cloudsql drives Connector.connect_async with asyncpg."""
    settings = Settings(
        gcp_cloudsql_instance="proj:reg:inst",
        database_user="u",
        database_password="p",
        database_name="db",
    )
    fake_connector = MagicMock()
    fake_conn = object()
    fake_connector.connect_async = AsyncMock(return_value=fake_conn)

    captured: dict[str, Any] = {}

    def _fake_create(url: str, **kwargs: Any) -> MagicMock:
        captured["url"] = url
        captured.update(kwargs)
        return MagicMock(name="engine")

    monkeypatch.setattr(cloudsql, "_Connector", lambda loop: fake_connector)
    monkeypatch.setattr(cloudsql, "create_async_engine", _fake_create)

    engine, connector = cloudsql.async_engine_for_cloudsql(settings)

    assert engine is not None
    assert captured["url"] == "postgresql+asyncpg://"
    assert "async_creator" in captured
    # Driving the creator calls connect_async with the instance + asyncpg driver.
    await captured["async_creator"]()
    fake_connector.connect_async.assert_awaited_once()
    call = fake_connector.connect_async.call_args
    assert call.args[0] == "proj:reg:inst"
    assert call.args[1] == "asyncpg"
    assert call.kwargs["user"] == "u"
    assert call.kwargs["password"] == "p"
    assert call.kwargs["db"] == "db"
    assert connector is fake_connector


async def test_cloudsql_engine_carries_server_settings_for_parity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """asyncpg server_settings (idle/lock timeouts) ride through connect_async."""
    settings = Settings(
        gcp_cloudsql_instance="proj:reg:inst",
        database_user="u",
        database_password="p",
        database_name="db",
        database_idle_in_transaction_timeout_ms=120_000,
        database_lock_timeout_ms=30_000,
    )
    fake_connector = MagicMock()
    fake_connector.connect_async = AsyncMock(return_value=object())
    captured: dict[str, Any] = {}

    def _fake_create(url: str, **kwargs: Any) -> MagicMock:
        captured.update(kwargs)
        return MagicMock()

    monkeypatch.setattr(cloudsql, "_Connector", lambda loop: fake_connector)
    monkeypatch.setattr(cloudsql, "create_async_engine", _fake_create)

    cloudsql.async_engine_for_cloudsql(settings)
    await captured["async_creator"]()
    call = fake_connector.connect_async.call_args
    assert call.kwargs["server_settings"] == {
        "idle_in_transaction_session_timeout": "120000",
        "lock_timeout": "30000",
    }


def test_get_engine_uses_cloudsql_when_instance_set(
    monkeypatch: pytest.MonkeyPatch, _holder_reset: Any
) -> None:
    """get_engine routes through the Cloud SQL builder when instance is armed."""
    monkeypatch.setattr(db_base.settings, "gcp_cloudsql_instance", "proj:reg:inst")
    built: dict[str, Any] = {}

    def _fake_builder(settings: Any, pool: str = "primary") -> Any:
        built["called"] = True
        engine = MagicMock(name="cloudsql_engine")
        engine.url = "postgresql+asyncpg://"
        return engine, MagicMock(name="connector")

    monkeypatch.setattr(db_base, "async_engine_for_cloudsql", _fake_builder)
    db_base.get_engine()
    assert built.get("called") is True


def test_get_engine_plain_dsn_when_instance_empty(
    monkeypatch: pytest.MonkeyPatch, _holder_reset: Any
) -> None:
    """When gcp_cloudsql_instance is empty the plain DSN path is unchanged."""
    monkeypatch.setattr(db_base.settings, "gcp_cloudsql_instance", "")
    captured: dict[str, Any] = {}

    def _fake_create(url: str, **kwargs: Any) -> MagicMock:
        captured["url"] = url
        return MagicMock(name="plain_engine")

    monkeypatch.setattr(db_base, "create_async_engine", _fake_create)
    # Sentinel: the Cloud SQL builder must NOT be called.
    monkeypatch.setattr(
        db_base,
        "async_engine_for_cloudsql",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("cloudsql path taken")),
    )
    db_base.get_engine()
    assert captured["url"].startswith("postgresql+asyncpg://")
    assert "proj" not in captured["url"]


# --- Fix R1: background pool sizing under Cloud SQL ---


async def test_cloudsql_engine_background_pool_uses_background_sizing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """async_engine_for_cloudsql(settings, 'background') uses background sizing."""
    settings = Settings(
        gcp_cloudsql_instance="proj:reg:inst",
        database_user="u",
        database_password="p",
        database_name="db",
        database_pool_size=10,
        database_max_overflow=20,
        database_background_pool_size=4,
        database_background_max_overflow=2,
    )
    fake_connector = MagicMock()
    fake_connector.connect_async = AsyncMock(return_value=object())
    captured: dict[str, Any] = {}

    def _fake_create(url: str, **kwargs: Any) -> MagicMock:
        captured.update(kwargs)
        return MagicMock()

    monkeypatch.setattr(cloudsql, "_Connector", lambda loop: fake_connector)
    monkeypatch.setattr(cloudsql, "create_async_engine", _fake_create)

    cloudsql.async_engine_for_cloudsql(settings, pool="background")

    assert captured["pool_size"] == 4
    assert captured["max_overflow"] == 2


async def test_cloudsql_engine_primary_pool_uses_primary_sizing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """async_engine_for_cloudsql(settings, 'primary') keeps primary sizing."""
    settings = Settings(
        gcp_cloudsql_instance="proj:reg:inst",
        database_user="u",
        database_password="p",
        database_name="db",
        database_pool_size=10,
        database_max_overflow=20,
        database_background_pool_size=4,
        database_background_max_overflow=2,
    )
    fake_connector = MagicMock()
    fake_connector.connect_async = AsyncMock(return_value=object())
    captured: dict[str, Any] = {}

    def _fake_create(url: str, **kwargs: Any) -> MagicMock:
        captured.update(kwargs)
        return MagicMock()

    monkeypatch.setattr(cloudsql, "_Connector", lambda loop: fake_connector)
    monkeypatch.setattr(cloudsql, "create_async_engine", _fake_create)

    cloudsql.async_engine_for_cloudsql(settings, pool="primary")

    assert captured["pool_size"] == 10
    assert captured["max_overflow"] == 20


def test_get_engine_background_passes_pool_to_cloudsql_builder(
    monkeypatch: pytest.MonkeyPatch, _holder_reset: Any
) -> None:
    """get_engine(pool='background') passes pool through to the Cloud SQL builder."""
    monkeypatch.setattr(db_base.settings, "gcp_cloudsql_instance", "proj:reg:inst")
    received: dict[str, Any] = {}

    def _fake_builder(settings: Any, pool: str = "primary") -> Any:
        received["pool"] = pool
        engine = MagicMock(name="cloudsql_engine")
        return engine, MagicMock(name="connector")

    monkeypatch.setattr(db_base, "async_engine_for_cloudsql", _fake_builder)
    db_base.get_engine(pool="background")
    assert received.get("pool") == "background"
