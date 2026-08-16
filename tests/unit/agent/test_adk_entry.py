"""Tests for roboco.agent.adk_entry — ADK runner loop, usage report, exit codes."""

from __future__ import annotations

import httpx
import pytest


class _FakeUsage:
    prompt_token_count = 12
    candidates_token_count = 34


class _FakeEvent:
    usage_metadata = _FakeUsage()
    turn_complete = True


class _FakeSession:
    id = "sess-1"


class _FakeSessionService:
    async def create_session(self, *, app_name, user_id, state=None, session_id=None):
        return _FakeSession()


def _setup_env(monkeypatch, tmp_path):
    monkeypatch.setenv("ROBOCO_ORCHESTRATOR_URL", "http://orch:8000")
    monkeypatch.setenv("ROBOCO_AGENT_ID", "77777777-7777-7777-7777-777777777777")
    monkeypatch.setenv("ROBOCO_AGENT_ROLE", "developer")
    monkeypatch.setenv("ROBOCO_AGENT_TOKEN", "UNSIGNED")
    monkeypatch.setenv("ROBOCO_INITIAL_PROMPT", "do the work")
    monkeypatch.setattr("roboco.agent.adk_entry.build_gateway_tools", lambda: [])
    monkeypatch.setattr("roboco.agent.adk_entry.build_git_tools", lambda: [])
    monkeypatch.setattr(
        "roboco.agent.adk_entry.InMemorySessionService", _FakeSessionService
    )


@pytest.mark.asyncio
async def test_main_runs_and_reports_usage(monkeypatch, tmp_path):
    _setup_env(monkeypatch, tmp_path)
    runs: list = []

    class _FakeRunner:
        def __init__(self, *, agent=None, app_name=None, session_service=None, **_):
            runs.append({"app_name": app_name})

        async def run_async(self, *, user_id, session_id, new_message=None, **_):
            runs.append({"user_id": user_id, "session_id": session_id})
            yield _FakeEvent()

    monkeypatch.setattr("roboco.agent.adk_entry.Runner", _FakeRunner)
    posted: dict = {}

    async def fake_post(self, url, **kw):
        posted["url"] = url
        posted["json"] = kw.get("json")
        return httpx.Response(200, json={"status": "ok"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    from roboco.agent.adk_entry import main

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
async def test_main_resource_exhausted_returns_75(monkeypatch, tmp_path):
    _setup_env(monkeypatch, tmp_path)

    class ResourceExhausted(Exception):
        pass

    class _FakeRunner:
        def __init__(self, **_):
            pass

        async def run_async(self, **_):
            raise ResourceExhausted("quota exceeded")
            yield  # pragma: no cover - make this an async generator

    monkeypatch.setattr("roboco.agent.adk_entry.Runner", _FakeRunner)

    async def fake_post(self, url, **kw):
        return httpx.Response(200, json={"status": "ok"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    from roboco.agent.adk_entry import main

    rc = await main()
    assert rc == 75


@pytest.mark.asyncio
async def test_main_unauthenticated_returns_78(monkeypatch, tmp_path):
    _setup_env(monkeypatch, tmp_path)

    class Unauthenticated(Exception):
        pass

    class _FakeRunner:
        def __init__(self, **_):
            pass

        async def run_async(self, **_):
            raise Unauthenticated("bad token")
            yield  # pragma: no cover

    monkeypatch.setattr("roboco.agent.adk_entry.Runner", _FakeRunner)

    async def fake_post(self, url, **kw):
        return httpx.Response(200, json={"status": "ok"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    from roboco.agent.adk_entry import main

    rc = await main()
    assert rc == 78


@pytest.mark.asyncio
async def test_main_propagates_unknown_exception(monkeypatch, tmp_path):
    _setup_env(monkeypatch, tmp_path)

    class _FakeRunner:
        def __init__(self, **_):
            pass

        async def run_async(self, **_):
            raise RuntimeError("boom")
            yield  # pragma: no cover

    monkeypatch.setattr("roboco.agent.adk_entry.Runner", _FakeRunner)

    async def fake_post(self, url, **kw):
        return httpx.Response(200, json={"status": "ok"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    from roboco.agent.adk_entry import main

    with pytest.raises(RuntimeError, match="boom"):
        await main()
