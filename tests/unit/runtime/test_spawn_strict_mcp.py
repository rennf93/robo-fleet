"""MCP config generation + no-provider spawn guard.

Leg D1 stripped the Claude CLI docker spawn path (the fall-through body in
``_spawn_container``); ADK_CLOUD_RUN is the live delivery spawn path. A
delivery spawn that resolves to no registered provider now raises a
RuntimeError instead of building a ``claude`` docker run.

The MCP-config generation tests below are unaffected (they exercise
``_generate_mcp_config``, not the deleted spawn arg builder).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from robofleet.config import settings
from robofleet.models.runtime import OrchestratorAgentConfig, SpawnGitContext
from robofleet.runtime.orchestrator import AgentOrchestrator


def _make_dev_config() -> OrchestratorAgentConfig:
    """Minimal AgentConfig for a developer with no registered provider."""
    return OrchestratorAgentConfig(
        agent_id="be-dev-1",
        blueprint_path=Path("/app/agents/blueprints/be-dev-1.md"),
        model="sonnet",
        mcp_config_path=Path("/app/mcp-config.json"),
        git_context=SpawnGitContext(
            project_slug="roboco-api",
            branch_name="feature/backend/TASK0001",
        ),
        # provider_type defaults to "anthropic" and no dedicated provider is
        # registered for it, so _provider_for returns None.
    )


class TestNoProviderSpawnRaises:
    """Leg D1: a delivery spawn with no registered provider raises RuntimeError
    instead of falling through to the (deleted) Claude CLI docker run path."""

    @pytest.mark.asyncio
    async def test_no_provider_delivery_spawn_raises(self) -> None:
        orch = AgentOrchestrator.__new__(AgentOrchestrator)
        # _provider_for returns None for ANTHROPIC (no dedicated provider
        # registered), so the spawn dispatch raises instead of building a
        # `claude` docker run.
        with (
            patch.object(orch, "_provider_for", return_value=None),
            pytest.raises(RuntimeError, match="No spawn backend"),
        ):
            await orch._spawn_container(_make_dev_config(), initial_prompt="do work")


class TestMcpConfigPinsBakedVenv:
    """#179: every generated MCP server launch must pin uv to the baked
    image venv so `uv run` (cwd = workspace) reuses /app/.venv instead of
    re-syncing the full dependency set (~350MB) on every spawn."""

    @pytest.mark.asyncio
    async def test_every_mcp_server_env_pins_uv_project_environment(self) -> None:
        orch = AgentOrchestrator.__new__(AgentOrchestrator)
        # be-dev-1 is a known agent (resolves role + uuid); generation is
        # otherwise pure (writes a json file and returns its path).
        config_path = await orch._generate_mcp_config("be-dev-1")
        config = json.loads(Path(config_path).read_text())
        servers = config["mcpServers"]
        assert servers, "expected at least the four core MCP servers"
        for name, spec in servers.items():
            assert spec["command"] == "uv", f"{name} should launch via uv"
            assert spec["env"].get("UV_PROJECT_ENVIRONMENT") == "/app/.venv", (
                f"MCP server {name!r} is missing UV_PROJECT_ENVIRONMENT="
                f"/app/.venv — without it `uv run` re-downloads deps into a "
                f"cwd-relative venv on every spawn (#179). env={spec['env']}"
            )
            # Pinning the env location is necessary but NOT sufficient: from a
            # workspace-clone cwd `uv run` still discovers the clone project and
            # re-syncs the pinned venv against its drifted lock, which stalls and
            # leaves the server stuck at status="pending" (zero gateway verbs).
            # `--no-sync` skips that resync — it must come right after `run`.
            assert spec["args"][:2] == ["run", "--no-sync"], (
                f"MCP server {name!r} must launch with `uv run --no-sync ...` so "
                f"a drifted workspace-clone lock can't trigger a resync stall; "
                f"got args={spec['args']}"
            )

    @pytest.mark.asyncio
    async def test_mcp_env_mirrors_flow_verb_timeout_settings(self) -> None:
        """flow_server.py (a subprocess, can't read Settings) mirrors the two
        server-side flow-verb timeout budgets via env so its client timeout
        stays coherent with operator tuning of either setting."""
        orch = AgentOrchestrator.__new__(AgentOrchestrator)
        config_path = await orch._generate_mcp_config("be-dev-1")
        config = json.loads(Path(config_path).read_text())
        env = config["mcpServers"]["roboco-flow"]["env"]
        assert env["ROBOFLEET_FLOW_VERB_TIMEOUT_SECONDS"] == str(
            settings.flow_verb_timeout_seconds
        )
        assert env["ROBOFLEET_FLOW_VERB_SLOW_TIMEOUT_SECONDS"] == str(
            settings.flow_verb_slow_timeout_seconds
        )
