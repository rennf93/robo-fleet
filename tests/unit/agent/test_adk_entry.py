"""Tests for robofleet.agent.adk_entry: ADK runner loop, usage report, exit codes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest


class _FakeUsage:
    prompt_token_count: int = 12
    candidates_token_count: int = 34


class _FakeEvent:
    usage_metadata: Any = _FakeUsage()
    turn_complete: bool = True


class _FakeSession:
    id: str = "sess-1"


class _FakeSessionService:
    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> _FakeSession:
        return _FakeSession()


def _setup_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ROBOFLEET_ORCHESTRATOR_URL", "http://orch:8000")
    monkeypatch.setenv("ROBOFLEET_AGENT_ID", "77777777-7777-7777-7777-777777777777")
    monkeypatch.setenv("ROBOFLEET_AGENT_ROLE", "developer")
    monkeypatch.setenv("ROBOFLEET_AGENT_TOKEN", "UNSIGNED")
    monkeypatch.setenv("ROBOFLEET_INITIAL_PROMPT", "do the work")
    monkeypatch.setattr("robofleet.agent.adk_entry.build_gateway_tools", lambda: [])
    monkeypatch.setattr("robofleet.agent.adk_entry.build_git_tools", lambda: [])
    monkeypatch.setattr(
        "robofleet.agent.adk_entry.InMemorySessionService", _FakeSessionService
    )


async def _fake_post_ok(self: httpx.AsyncClient, url: str, **kw: Any) -> httpx.Response:
    return httpx.Response(200, json={"status": "ok"})


@pytest.mark.asyncio
async def test_main_runs_and_reports_usage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _setup_env(monkeypatch, tmp_path)
    runs: list[dict[str, Any]] = []

    class _FakeRunner:
        def __init__(
            self,
            *,
            agent: Any = None,
            app_name: str | None = None,
            session_service: Any = None,
            **_: Any,
        ) -> None:
            runs.append({"app_name": app_name})

        async def run_async(
            self,
            *,
            user_id: str,
            session_id: str,
            new_message: Any = None,
            **_: Any,
        ) -> Any:
            runs.append({"user_id": user_id, "session_id": session_id})
            yield _FakeEvent()

    monkeypatch.setattr("robofleet.agent.adk_entry.Runner", _FakeRunner)
    posted: dict[str, Any] = {}

    async def fake_post(self: httpx.AsyncClient, url: str, **kw: Any) -> httpx.Response:
        posted["url"] = url
        posted["json"] = kw.get("json")
        return httpx.Response(200, json={"status": "ok"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    from robofleet.agent.adk_entry import main

    rc = await main()
    assert rc == 0
    assert len(runs) == 2  # one __init__, one run_async
    assert posted["url"] == "http://orch:8000/api/v1/usage/report"
    body = posted["json"]
    assert body["turns"] == 1
    assert body["tokens_input"] == 12
    assert body["tokens_output"] == 34
    # cache fields present and zero (no cache metadata on the fake event)
    assert body["tokens_cache_read"] == 0
    assert body["tokens_cache_write"] == 0


@pytest.mark.asyncio
async def test_main_resource_exhausted_returns_75(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _setup_env(monkeypatch, tmp_path)

    class ResourceExhausted(Exception):
        pass

    class _FakeRunner:
        def __init__(self, **_: Any) -> None:
            pass

        async def run_async(self, **_: Any) -> Any:
            # Yield once so this is an async generator (one None event is
            # harmless to _accumulate), then raise on the next iteration.
            yield None
            raise ResourceExhausted("quota exceeded")

    monkeypatch.setattr("robofleet.agent.adk_entry.Runner", _FakeRunner)
    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post_ok)
    from robofleet.agent.adk_entry import main

    rc = await main()
    assert rc == 75


@pytest.mark.asyncio
async def test_main_unauthenticated_returns_78(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _setup_env(monkeypatch, tmp_path)

    class Unauthenticated(Exception):
        pass

    class _FakeRunner:
        def __init__(self, **_: Any) -> None:
            pass

        async def run_async(self, **_: Any) -> Any:
            yield None
            raise Unauthenticated("bad token")

    monkeypatch.setattr("robofleet.agent.adk_entry.Runner", _FakeRunner)
    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post_ok)
    from robofleet.agent.adk_entry import main

    rc = await main()
    assert rc == 78


@pytest.mark.asyncio
async def test_main_propagates_unknown_exception(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _setup_env(monkeypatch, tmp_path)

    class _FakeRunner:
        def __init__(self, **_: Any) -> None:
            pass

        async def run_async(self, **_: Any) -> Any:
            yield None
            raise RuntimeError("boom")

    monkeypatch.setattr("robofleet.agent.adk_entry.Runner", _FakeRunner)
    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post_ok)
    from robofleet.agent.adk_entry import main

    with pytest.raises(RuntimeError, match="boom"):
        await main()
