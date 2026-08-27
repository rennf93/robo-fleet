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
            runs.append(
                {
                    "user_id": user_id,
                    "session_id": session_id,
                    "new_message": new_message,
                }
            )
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


def test_on_tool_error_returns_response_instead_of_raising() -> None:
    """An unknown tool name (or a raising tool) becomes a function RESPONSE the
    model can read and recover from, not a dead run + Cloud Run retry."""
    from robofleet.agent.adk_entry import _on_tool_error

    err = ValueError("Tool 'bash' not found.\nAvailable tools: note, evidence")
    resp = _on_tool_error(
        tool=object(), args={"cmd": "ls"}, tool_context=object(), error=err
    )
    assert resp is not None
    assert resp["error"] == "ValueError"
    assert "Available tools: note, evidence" in resp["message"]
    assert resp["remediate"]
    # A dead orchestrator is not a hallucinated tool: let ADK re-raise it.
    transport = httpx.ConnectError("orchestrator unreachable")
    assert (
        _on_tool_error(tool=object(), args={}, tool_context=object(), error=transport)
        is None
    )


@pytest.mark.asyncio
async def test_main_wires_on_tool_error_callback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _setup_env(monkeypatch, tmp_path)
    captured: dict[str, Any] = {}

    class _FakeAgent:
        def __init__(self, **kw: Any) -> None:
            captured.update(kw)
            self.tools = kw.get("tools", [])

    class _FakeRunner:
        def __init__(self, **_: Any) -> None:
            pass

        async def run_async(self, **_: Any) -> Any:
            yield _FakeEvent()

    monkeypatch.setattr("robofleet.agent.adk_entry.LlmAgent", _FakeAgent)
    monkeypatch.setattr("robofleet.agent.adk_entry.Runner", _FakeRunner)
    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post_ok)
    from robofleet.agent.adk_entry import _on_tool_error, main

    assert await main() == 0
    assert captured["on_tool_error_callback"] is _on_tool_error


def test_headers_carry_team_for_usage_post(monkeypatch: pytest.MonkeyPatch) -> None:
    """The usage POST must send X-Agent-Team: the token is signed over
    (id, role, team) and the gateway 401s a team-less request."""
    from robofleet.agent.adk_entry import _headers

    monkeypatch.setenv("ROBOFLEET_AGENT_ID", "77777777-7777-7777-7777-777777777777")
    monkeypatch.setenv("ROBOFLEET_AGENT_ROLE", "developer")
    monkeypatch.setenv("ROBOFLEET_AGENT_TEAM", "backend")
    monkeypatch.setenv("ROBOFLEET_AGENT_TOKEN", "signed")
    h = _headers()
    assert h["X-Agent-Team"] == "backend"
    assert h["X-Agent-Token"] == "signed"
    monkeypatch.delenv("ROBOFLEET_AGENT_TEAM")
    assert "X-Agent-Team" not in _headers()


def test_after_tool_loop_breaker_warns_then_halts() -> None:
    """Consecutive rejections of ONE tool: silent below the warn line, a
    loop_warning merged into the response from _LOOP_WARN_AT, ToolLoopError at
    _LOOP_HALT_AT; a success or a different tool resets the streak."""
    from robofleet.agent import adk_entry
    from robofleet.agent.adk_entry import ToolLoopError, _on_after_tool

    class _Tool:
        def __init__(self, name: str) -> None:
            self.name = name

    note, ok = _Tool("note"), {"status": "noted", "error": None}
    bad = {"status": None, "error": "invalid_state", "message": "done required"}
    adk_entry._loop.update(tool=None, count=0)
    for _ in range(adk_entry._LOOP_WARN_AT - 1):
        assert _on_after_tool(note, {}, object(), bad) is None
    warned = _on_after_tool(note, {}, object(), bad)
    assert warned is not None and "loop_warning" in warned
    assert warned["error"] == "invalid_state"
    assert _on_after_tool(note, {}, object(), ok) is None  # reset
    assert adk_entry._loop["count"] == 0
    for _ in range(adk_entry._LOOP_HALT_AT - 1):
        _on_after_tool(note, {}, object(), bad)
    assert (
        _on_after_tool(_Tool("evidence"), {}, object(), bad) is None
    )  # other tool resets
    for _ in range(adk_entry._LOOP_HALT_AT - 1):
        _on_after_tool(note, {}, object(), bad)
    with pytest.raises(ToolLoopError):
        _on_after_tool(note, {}, object(), bad)
    # The tool-error callback must not swallow the cut into a tool response.
    from robofleet.agent.adk_entry import _on_tool_error

    assert (
        _on_tool_error(
            tool=note, args={}, tool_context=object(), error=ToolLoopError("x")
        )
        is None
    )


@pytest.mark.asyncio
async def test_main_tool_loop_cut_exits_zero_and_reports_usage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A ToolLoopError wrapped by ADK ends the run with exit 0 (no Cloud Run
    retry) and still posts usage with exit_reason=tool_loop."""
    _setup_env(monkeypatch, tmp_path)
    posts: list[dict[str, Any]] = []

    async def fake_post(self: httpx.AsyncClient, url: str, **kw: Any) -> httpx.Response:
        posts.append({"url": url, "json": kw.get("json", {})})
        return httpx.Response(200, json={"status": "ok"})

    class _Wrapped(Exception):
        def __init__(self, error: BaseException) -> None:
            super().__init__("Dynamic node robofleet_agent failed")
            self.error = error

    class _FakeAgent:
        def __init__(self, **kw: Any) -> None:
            self.tools = kw.get("tools", [])
            assert kw["after_tool_callback"].__name__ == "_on_after_tool"

    class _FakeRunner:
        def __init__(self, **_: Any) -> None:
            pass

        async def run_async(self, **_: Any) -> Any:
            yield _FakeEvent()
            from robofleet.agent.adk_entry import ToolLoopError

            raise _Wrapped(ToolLoopError("note rejected 12 calls in a row"))

    monkeypatch.setattr("robofleet.agent.adk_entry.LlmAgent", _FakeAgent)
    monkeypatch.setattr("robofleet.agent.adk_entry.Runner", _FakeRunner)
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    from robofleet.agent.adk_entry import main

    assert await main() == 0
    usage = next(p["json"] for p in posts if p["url"].endswith("/usage/report"))
    assert usage["exit_reason"] == "tool_loop"
