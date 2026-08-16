"""POST /api/v1/usage/report persists provider-backed agent token counts.

Provider-backed (Cloud Run Job / ADK_CLOUD_RUN) agents have no :9000 SDK
server to poll, so the agent POSTs its final cumulative counts and the
orchestrator persists them onto the open agent_spawn_sessions row.

Route-level unit test with a mocked DbSession (no DB harness in
tests/unit/api/ — there is no conftest.py seeding client/db_session fixtures
here, so the plan's DB-backed path is unavailable). The fake session records
the UPDATE values; resolve_agent_identity is patched so the UUID->slug hop
needs no AgentTable query. Asserts the route runs the UPDATE with the six
body fields, returns {"status":"ok","matched":True}; a missing open row
returns matched=False, never 500.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient
from roboco.api.routes.v1 import usage as usage_v1_module
from roboco.db.base import get_db_committed

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

_AGENT_UUID = UUID("00000000-0000-0000-0000-000000000001")
_AGENT_SLUG = "be-dev-1"
_SESSION_ID = UUID("00000000-0000-0000-0000-000000000aaa")
# SELECT (open session) then UPDATE (six columns) => two execute calls.
_EXPECTED_EXECUTE_CALLS = 2

_BODY = {
    "turns": 3,
    "tool_calls": 12,
    "tokens_input": 1000,
    "tokens_output": 500,
    "tokens_cache_read": 0,
    "tokens_cache_write": 0,
}


def _make_fake_db(session_id: UUID | None) -> MagicMock:
    """Build a fake AsyncSession whose execute handles SELECT then UPDATE.

    The first execute (the spawn-session SELECT) returns session_id (or None);
    the second (the UPDATE) returns a no-op result. commit is an AsyncMock.
    """
    db = MagicMock()
    select_result = MagicMock()
    select_result.scalar_one_or_none.return_value = session_id
    update_result = MagicMock()
    db.execute = AsyncMock(side_effect=[select_result, update_result])
    db.commit = AsyncMock()
    return db


def _override_db_factory(db: MagicMock) -> Callable[[], AsyncIterator[MagicMock]]:
    async def _override() -> AsyncIterator[MagicMock]:
        yield db

    return _override


@pytest.mark.asyncio
async def test_usage_report_persists_tokens() -> None:
    db = _make_fake_db(_SESSION_ID)
    app = FastAPI()
    app.include_router(usage_v1_module.router)
    app.dependency_overrides[get_db_committed] = _override_db_factory(db)
    with patch(
        f"{usage_v1_module.__name__}.resolve_agent_identity",
        AsyncMock(return_value=(_AGENT_UUID, _AGENT_SLUG)),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/usage/report",
                json=_BODY,
                headers={"X-Agent-ID": str(_AGENT_UUID), "X-Agent-Role": "developer"},
            )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json() == {"status": "ok", "matched": True}
    # SELECT (open session) then UPDATE (six columns) => two execute calls,
    # plus one commit. The UPDATE statement is the second execute call.
    assert db.execute.await_count == _EXPECTED_EXECUTE_CALLS
    update_stmt = db.execute.await_args_list[1].args[0]
    # Compile the UPDATE to SQL and confirm every body field is present —
    # avoids brittle introspection of SQLAlchemy's internal values map.
    compiled = update_stmt.compile(compile_kwargs={"literal_binds": True})
    sql = str(compiled)
    for field in (
        "turns",
        "tool_calls",
        "tokens_input",
        "tokens_output",
        "tokens_cache_read",
        "tokens_cache_write",
    ):
        assert field in sql
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_usage_report_missing_session_returns_matched_false() -> None:
    db = _make_fake_db(None)
    app = FastAPI()
    app.include_router(usage_v1_module.router)
    app.dependency_overrides[get_db_committed] = _override_db_factory(db)
    with patch(
        f"{usage_v1_module.__name__}.resolve_agent_identity",
        AsyncMock(return_value=(_AGENT_UUID, _AGENT_SLUG)),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/usage/report",
                json=_BODY,
                headers={"X-Agent-ID": str(_AGENT_UUID), "X-Agent-Role": "developer"},
            )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json() == {"status": "ok", "matched": False}
    # No open row => no UPDATE, no commit.
    assert db.execute.await_count == 1
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_usage_report_unresolved_agent_returns_matched_false() -> None:
    db = _make_fake_db(_SESSION_ID)
    app = FastAPI()
    app.include_router(usage_v1_module.router)
    app.dependency_overrides[get_db_committed] = _override_db_factory(db)
    with patch(
        f"{usage_v1_module.__name__}.resolve_agent_identity",
        AsyncMock(return_value=None),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/usage/report",
                json=_BODY,
                headers={"X-Agent-ID": str(_AGENT_UUID), "X-Agent-Role": "developer"},
            )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json() == {"status": "ok", "matched": False}
    db.execute.assert_not_awaited()
