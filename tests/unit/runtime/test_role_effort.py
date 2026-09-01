"""Per-role effort map + no-provider spawn guard.

Leg D1 stripped the Claude CLI docker spawn path (the fall-through in
``_spawn_container``) along with ``_append_image_and_claude_args`` (which
applied ``ROLE_EFFORT_MAP`` to the ``--effort`` flag). ADK_CLOUD_RUN is the
live delivery spawn path. The ``ROLE_EFFORT_MAP`` data table still ships (it
is a pure policy map, not bound to the deleted arg builder), so the shipped
value assertion below stays; the spawn-argv ``--effort`` tests are replaced by
a guard that a no-provider delivery spawn raises RuntimeError.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from robofleet.models.runtime import (
    ROLE_EFFORT_MAP,
    OrchestratorAgentConfig,
    SpawnGitContext,
)
from robofleet.runtime.orchestrator import AgentOrchestrator


def _config(agent_id: str) -> OrchestratorAgentConfig:
    return OrchestratorAgentConfig(
        agent_id=agent_id,
        blueprint_path=Path(f"/app/agents/blueprints/{agent_id}.md"),
        model="sonnet",
        mcp_config_path=Path("/app/mcp-config.json"),
        git_context=SpawnGitContext(
            project_slug="robofleet-api",
            branch_name="feature/backend/TASK0001",
        ),
    )


def test_shipped_map_sets_cell_pm_to_medium() -> None:
    # The shipped ROLE_EFFORT_MAP routes cell_pm to medium.
    assert ROLE_EFFORT_MAP.get("cell_pm") == "medium"


@pytest.mark.asyncio
async def test_no_provider_delivery_spawn_raises() -> None:
    """Leg D1: a delivery spawn with no registered provider raises RuntimeError
    instead of falling through to the (deleted) Claude CLI docker run path."""
    orch = AgentOrchestrator.__new__(AgentOrchestrator)
    with (
        patch.object(orch, "_provider_for", return_value=None),
        pytest.raises(RuntimeError, match="No spawn backend"),
    ):
        await orch._spawn_container(_config("be-dev-1"), initial_prompt="work")
