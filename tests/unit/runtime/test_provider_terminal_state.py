"""Provider-backed terminal state: _check_health synthesizes exit_code.

A finished one-shot Cloud Run Job execution exposes no container exit code, so
_check_health -> _handle_stopped_container keys graceful-vs-crash on the
provider's execution_outcome (0 succeeded, 1 failed). A normally-completed ADK
agent (outcome 0) is graceful -> no respawn; a failed one (outcome 1) -> crash
path -> retry/escalate. Also covers the pushed exit_reason overload break for
provider-backed agents (which have no container exit code 75/78).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from roboco.models.runtime import AgentInstance, OrchestratorAgentConfig
from roboco.runtime.orchestrator import AgentOrchestrator, AgentState


def _make_orchestrator() -> AgentOrchestrator:
    # __new__ + skip __init__: avoid all constructor I/O.
    orch = AgentOrchestrator.__new__(AgentOrchestrator)
    orch._instances = {}
    orch._lock = asyncio.Lock()
    orch._bg_tasks = set()
    orch._running = True
    return orch


def _instance() -> AgentInstance:
    return AgentInstance(
        agent_id="be-dev-1",
        state=AgentState.ACTIVE,
        container_id="projects/p/locations/e/jobs/j/executions/x",
        config=OrchestratorAgentConfig(
            agent_id="be-dev-1",
            blueprint_path=Path("/tmp/blueprint.md"),
            model="gemini-3.5-flash",
            provider_type="adk_cloud_run",
        ),
        current_task_id=None,
        usage_session_id=None,
        error_count=0,
    )


class _FakeProvider:
    """Provider stub exposing execution_outcome (None=running, 0/1=done)."""

    def __init__(self, outcome: int | None) -> None:
        self.execution_outcome = AsyncMock(return_value=outcome)


def _kwargs_of(mock: AsyncMock) -> dict[str, object]:
    """Return the mock's last call kwargs, or {} if it was never called."""
    call = mock.await_args
    return dict(call.kwargs) if call is not None else {}


def _wire_common(
    monkeypatch: pytest.MonkeyPatch,
    orch: AgentOrchestrator,
    outcome: int | None,
) -> dict[str, AsyncMock]:
    """Wire the _check_health + _handle_stopped_container deps on orch."""
    inst = _instance()
    orch._instances["be-dev-1"] = inst
    # monkeypatch.setattr (not bare assignment) so mypy's method-assign check
    # accepts the override - same pattern as test_parked_spawn_shortcut.
    monkeypatch.setattr(
        orch, "_provider_for_instance", lambda _aid: _FakeProvider(outcome)
    )
    mocks: dict[str, AsyncMock] = {}
    # _check_health tail: liveness bookkeeping not under test.
    monkeypatch.setattr(orch, "_check_loop_liveness", lambda: None)
    # _handle_stopped_container internals:
    park_known = AsyncMock(return_value=False)
    monkeypatch.setattr(orch, "_maybe_park_for_known_exit", park_known)
    park_exit = AsyncMock(return_value=False)
    monkeypatch.setattr(orch, "_maybe_park_for_exit_error", park_exit)
    park_pushed = AsyncMock(return_value=False)
    monkeypatch.setattr(orch, "_maybe_park_provider_for_pushed_reason", park_pushed)
    finalize = AsyncMock()
    monkeypatch.setattr(orch, "_finalize_spawn_session", finalize)
    crash = AsyncMock()
    monkeypatch.setattr(orch, "_crash_retry_or_escalate", crash)
    mocks["park_known"] = park_known
    mocks["park_pushed"] = park_pushed
    mocks["finalize"] = finalize
    mocks["crash"] = crash
    return mocks


@pytest.mark.asyncio
async def test_finished_success_is_graceful_no_respawn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orch = _make_orchestrator()
    mocks = _wire_common(monkeypatch, orch, outcome=0)

    await orch._check_health()

    # Graceful (exit_code 0) -> no respawn, finalize called with "completed".
    assert mocks["crash"].await_count == 0
    assert mocks["finalize"].await_count == 1
    assert _kwargs_of(mocks["finalize"]).get("exit_reason") == "completed"
    assert orch._instances["be-dev-1"].state == AgentState.OFFLINE


@pytest.mark.asyncio
async def test_finished_fail_is_crash_respawn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orch = _make_orchestrator()
    mocks = _wire_common(monkeypatch, orch, outcome=1)

    await orch._check_health()

    # Crash (exit_code 1) -> respawn path, finalize called with "crashed".
    assert mocks["crash"].await_count == 1
    assert _kwargs_of(mocks["finalize"]).get("exit_reason") == "crashed"


@pytest.mark.asyncio
async def test_running_execution_skips_stopped_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orch = _make_orchestrator()
    mocks = _wire_common(monkeypatch, orch, outcome=None)  # still running

    await orch._check_health()

    # Still running -> _handle_stopped_container never called.
    assert mocks["finalize"].await_count == 0
    assert mocks["crash"].await_count == 0
    assert orch._instances["be-dev-1"].state == AgentState.ACTIVE


@pytest.mark.asyncio
async def test_pushed_rate_limit_reason_parks_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider-backed agent that pushed exit_reason='rate_limited' parks
    the provider (mirrors docker's exit-75) instead of crash-respawning.
    """
    orch = _make_orchestrator()
    # outcome=1 (the execution failed on the rate-limit exit), but the pushed
    # reason says rate_limited -> park, don't respawn.
    mocks = _wire_common(monkeypatch, orch, outcome=1)
    # Override the pushed-reason park to return True (it matched + parked).
    mocks["park_pushed"].return_value = True

    await orch._check_health()

    # Parked -> no crash respawn, no finalize (session left open for the probe
    # loop to revive), same shape as the docker 75/78 early-return.
    assert mocks["park_pushed"].await_count == 1
    assert mocks["crash"].await_count == 0
    assert mocks["finalize"].await_count == 0
