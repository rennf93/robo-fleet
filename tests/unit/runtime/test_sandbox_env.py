"""Sandbox marker env: ``_append_sandbox_marker_env`` + the no-provider spawn
guard.

An opted-in spawn injects a cheap ``ROBOFLEET_SANDBOX_SERVICES_AVAILABLE``
marker (never prod creds; actual provisioning is on-demand via
``request_sandbox``).

Leg D1 stripped the Claude CLI docker spawn path (the fall-through in
``_spawn_container``) that previously branched on
``config.sandbox_available_services`` to choose the marker env vs the legacy
``_append_gate_env``. That branch is gone with the fall-through; the marker
helper itself stays (it is a pure function tested directly below). The
``_spawn_container`` integration tests are replaced by a guard that a
no-provider delivery spawn raises RuntimeError.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from robofleet.models.runtime import OrchestratorAgentConfig
from robofleet.runtime.orchestrator import AgentOrchestrator


def _config(
    sandbox_available_services: list[str] | None = None,
) -> OrchestratorAgentConfig:
    return OrchestratorAgentConfig(
        agent_id="dev-1",
        blueprint_path=Path(),
        mcp_config_path=Path("/tmp/mcp.json"),
        sandbox_available_services=sandbox_available_services or [],
    )


def test_append_sandbox_marker_env_lists_services() -> None:
    cmd: list[str] = []
    AgentOrchestrator._append_sandbox_marker_env(cmd, ["postgres", "redis"])

    assert "ROBOFLEET_SANDBOX_SERVICES_AVAILABLE=postgres,redis" in cmd


def test_append_sandbox_marker_env_single_service() -> None:
    cmd: list[str] = []
    AgentOrchestrator._append_sandbox_marker_env(cmd, ["mongo"])

    assert "ROBOFLEET_SANDBOX_SERVICES_AVAILABLE=mongo" in cmd


@pytest.mark.asyncio
async def test_no_provider_delivery_spawn_raises() -> None:
    """Leg D1: a delivery spawn with no registered provider raises RuntimeError
    instead of falling through to the (deleted) Claude CLI docker run path,
    regardless of the sandbox-available marker on the config."""
    orch = AgentOrchestrator.__new__(AgentOrchestrator)
    with (
        patch.object(orch, "_provider_for", return_value=None),
        pytest.raises(RuntimeError, match="No spawn backend"),
    ):
        await orch._spawn_container(_config(["postgres"]))
