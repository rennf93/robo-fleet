"""Provider lifecycle routing: stop/health/remove go through the spawn provider.

Pins the seam introduced in Task 2.3: when an instance is backed by a dedicated
provider (ADK_CLOUD_RUN today, the same registry GROK/CODEX/GEMINI/KIMI use),
the orchestrator's stop/health/remove/probe paths must route through that
provider instead of the docker subprocess path. `get_or_none` returning None is
the "use docker" signal, so the ANTHROPIC/local path is byte-for-byte unchanged.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from roboco.runtime.orchestrator import AgentOrchestrator


def _make_orch() -> MagicMock:
    """A bare MagicMock with the few real attrs stop_agent/_check_health touch."""
    orch_obj = MagicMock()
    orch_obj._instances = {}
    orch_obj._lock = asyncio.Lock()
    orch_obj._finalize_spawn_session = AsyncMock()
    orch_obj._provider_for = MagicMock(return_value=None)
    return orch_obj


@pytest.mark.asyncio
async def test_stop_routes_through_provider_when_registered() -> None:
    """When _provider_for_instance returns a provider, stop_agent calls
    provider.stop and does NOT reach the docker stop/kill/remove block."""
    fake_provider = MagicMock()
    fake_provider.stop = AsyncMock()
    inst = MagicMock()
    inst.container_id = "exec-1"
    inst.config.provider_type = "adk_cloud_run"
    inst.current_task_id = None

    orch_obj = _make_orch()
    orch_obj._instances = {"be-dev-1": inst}
    orch_obj._provider_for_instance = MagicMock(return_value=fake_provider)

    await AgentOrchestrator.stop_agent(orch_obj, "be-dev-1", release_claim=False)

    fake_provider.stop.assert_awaited_once()
    # The docker stop/kill path runs asyncio.create_subprocess_exec("docker", ...)
    # which we did NOT patch -> it would raise. Not raising proves we skipped it.


@pytest.mark.asyncio
async def test_provider_for_instance_returns_none_for_docker() -> None:
    """An ANTHROPIC (docker-path) instance resolves to no provider."""
    inst = MagicMock()
    inst.config.provider_type = "anthropic"

    orch_obj = MagicMock(spec=AgentOrchestrator)
    orch_obj._instances = {"be-dev-1": inst}
    orch_obj._provider_for = MagicMock(return_value=None)

    assert AgentOrchestrator._provider_for_instance(orch_obj, "be-dev-1") is None


@pytest.mark.asyncio
async def test_check_health_routes_through_provider() -> None:
    """A provider-backed ACTIVE instance is health-checked via the provider,
    not via _inspect_container_state (docker)."""
    fake_provider = MagicMock()
    fake_provider.health_check = AsyncMock(return_value=True)
    inst = MagicMock()
    inst.state = MagicMock()  # will compare against AgentState.ACTIVE below
    inst.container_id = "exec-1"
    inst.config.provider_type = "adk_cloud_run"

    orch_obj = _make_orch()
    orch_obj._instances = {"be-dev-1": inst}
    orch_obj._provider_for_instance = MagicMock(return_value=fake_provider)
    # Make the state membership check pass: _check_health tests
    # `instance.state not in (AgentState.ACTIVE, AgentState.WAITING_SHORT)`.
    from roboco.models.runtime import OrchestratorAgentState as State

    inst.state = State.ACTIVE
    # If the docker path ran, this would raise (no asyncio patch). It must not.
    await AgentOrchestrator._check_health(orch_obj)
    fake_provider.health_check.assert_awaited_once()
