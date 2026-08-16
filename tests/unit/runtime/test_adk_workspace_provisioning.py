"""Tests for the ADK spawn branch workspace provisioning (Task F3, Part 3).

The ADK branch of ``_generate_mcp_config`` early-returns to
``_generate_adk_manifest``. Before that return, it must provision the per-agent
clone onto the Filestore NFS share (``ensure_workspace``) for roles that carry a
workspace, mirroring the docker path's ``_ensure_worktree_before_spawn``. These
tests isolate the provisioning call: ``_generate_adk_manifest`` is short-circuited
so the assertion targets ``ensure_workspace`` call/no-call only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from robofleet.models.base import ModelProvider
from robofleet.models.runtime import SpawnGitContext
from robofleet.runtime.orchestrator import AgentOrchestrator

_SLUG = "be-dev-1"

# Module-level call recorder: the ADK branch constructs WorkspaceService(db)
# inside the get_db_context block, so the test cannot hold the instance directly.
_ensured: list[tuple[str, str]] = []


class _FakeWs:
    """Records ensure_workspace calls into the module-level _ensured list."""

    def __init__(self, _db: Any) -> None:
        pass

    async def ensure_workspace(self, project_slug: str, agent_id: str) -> Path:
        _ensured.append((project_slug, agent_id))
        return Path("/data/workspaces") / project_slug / agent_id


class _FakeDbContext:
    """Async context manager yielding a dummy db session."""

    async def __aenter__(self) -> Any:
        return None

    async def __aexit__(self, *exc: object) -> None:
        return None


async def _fake_adk_manifest(
    _self: AgentOrchestrator,
    _agent_id: str,
    _git_context: SpawnGitContext | None,
    _task_id: str | None,
) -> Path:
    """Stand-in for _generate_adk_manifest: no role_config / compose_prompt."""
    return Path("/tmp/fake-adk-manifest.json")


@pytest.fixture(autouse=True)
def _reset_ensured() -> None:
    _ensured.clear()


@pytest.mark.asyncio
async def test_adk_spawn_provisions_workspace_for_developer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADK spawn calls ensure_workspace before _generate_adk_manifest for a
    developer role with a project_slug (clone lands on Filestore before the
    Cloud Run Job starts)."""
    monkeypatch.setattr("robofleet.db.base.get_db_context", _FakeDbContext)
    monkeypatch.setattr("robofleet.services.workspace.WorkspaceService", _FakeWs)
    monkeypatch.setattr(
        "robofleet.runtime.orchestrator.get_agent_role", lambda _s: "developer"
    )
    monkeypatch.setattr(AgentOrchestrator, "_generate_adk_manifest", _fake_adk_manifest)

    orch = AgentOrchestrator.__new__(AgentOrchestrator)
    await orch._generate_mcp_config(
        _SLUG,
        SpawnGitContext(project_slug="roboco"),
        provider_type=ModelProvider.ADK_CLOUD_RUN.value,
    )

    assert _ensured == [("roboco", _SLUG)]


@pytest.mark.asyncio
async def test_adk_spawn_skips_workspace_for_qa(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADK spawn skips ensure_workspace for a no-workspace role (qa): the guard
    only provisions for roles in _ROLES_WITH_AGENT_WORKSPACE /
    _ROLES_WITH_CELL_WORKSPACE."""
    monkeypatch.setattr("robofleet.db.base.get_db_context", _FakeDbContext)
    monkeypatch.setattr("robofleet.services.workspace.WorkspaceService", _FakeWs)
    monkeypatch.setattr(
        "robofleet.runtime.orchestrator.get_agent_role", lambda _s: "qa"
    )
    monkeypatch.setattr(AgentOrchestrator, "_generate_adk_manifest", _fake_adk_manifest)

    orch = AgentOrchestrator.__new__(AgentOrchestrator)
    await orch._generate_mcp_config(
        _SLUG,
        SpawnGitContext(project_slug="roboco"),
        provider_type=ModelProvider.ADK_CLOUD_RUN.value,
    )

    assert _ensured == []


@pytest.mark.asyncio
async def test_adk_spawn_skips_workspace_without_project_slug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADK spawn skips ensure_workspace when there is no project_slug (branchless
    / idle spawn): nothing to clone."""
    monkeypatch.setattr("robofleet.db.base.get_db_context", _FakeDbContext)
    monkeypatch.setattr("robofleet.services.workspace.WorkspaceService", _FakeWs)
    monkeypatch.setattr(
        "robofleet.runtime.orchestrator.get_agent_role", lambda _s: "developer"
    )
    monkeypatch.setattr(AgentOrchestrator, "_generate_adk_manifest", _fake_adk_manifest)

    orch = AgentOrchestrator.__new__(AgentOrchestrator)
    await orch._generate_mcp_config(
        _SLUG,
        None,
        provider_type=ModelProvider.ADK_CLOUD_RUN.value,
    )

    assert _ensured == []
