"""``GitService.get_workspace``'s no-``agent_id`` branch trusts
``project.workspace_path`` with only ``.exists()`` — no containment check.

Mirrors ``open_conventions_pr``'s existing scope guard
(test_git_conventions_pr_workspace_scope.py): a ``workspace_path`` outside
``{workspaces_root}/{project_slug}`` is never trusted as-is. Here there is no
explicit ``workspace`` argument to fall back to, so an out-of-root value falls
back to the derived in-root path instead of refusing outright.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from robofleet.services import git as git_module
from robofleet.services.base import ValidationError
from robofleet.services.git import GitService

if TYPE_CHECKING:
    from pathlib import Path


def _svc(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    workspace_path: str,
    slug: str = "g-proj",
) -> GitService:
    svc = GitService.__new__(GitService)
    svc.session = AsyncMock()
    monkeypatch.setattr(git_module.settings, "workspaces_root", str(root))
    project = MagicMock()
    project.slug = slug
    project.workspace_path = workspace_path
    project_service = MagicMock()
    project_service.get_by_slug = AsyncMock(return_value=project)
    monkeypatch.setattr(git_module, "get_project_service", lambda _s: project_service)
    return svc


@pytest.mark.asyncio
async def test_contained_workspace_path_used_as_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspaces"
    ws = root / "g-proj"
    ws.mkdir(parents=True)
    svc = _svc(monkeypatch, root, str(ws))

    result = await svc.get_workspace("g-proj")

    assert result == ws


@pytest.mark.asyncio
async def test_out_of_root_workspace_path_falls_back_to_derived(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspaces"
    derived = root / "g-proj"
    derived.mkdir(parents=True)
    outside = tmp_path / "outside-repo"
    outside.mkdir()
    svc = _svc(monkeypatch, root, str(outside))

    result = await svc.get_workspace("g-proj")

    assert result == derived


@pytest.mark.asyncio
async def test_out_of_root_workspace_path_raises_when_derived_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspaces"
    root.mkdir()
    outside = tmp_path / "outside-repo"
    outside.mkdir()
    svc = _svc(monkeypatch, root, str(outside))

    with pytest.raises(ValidationError, match="does not exist"):
        await svc.get_workspace("g-proj")


@pytest.mark.asyncio
async def test_other_projects_tree_falls_back_to_derived(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """workspace_path under workspaces_root but inside ANOTHER project's tree
    is still out-of-root for THIS project — falls back, never trusted."""
    root = tmp_path
    derived = root / "g-proj"
    derived.mkdir(parents=True)
    other = root / "other-proj" / "backend" / "be-dev-1"
    other.mkdir(parents=True)
    svc = _svc(monkeypatch, root, str(other))

    result = await svc.get_workspace("g-proj")

    assert result == derived
