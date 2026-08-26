"""``SetWorkspaceRequest.workspace_path`` had no constraint — a PM-gated
``POST /projects/{id}/workspace`` call could set any string, later trusted
by ``GitService.get_workspace``'s no-agent branch with only ``.exists()``.
Pins the validator's accept/reject boundary."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError
from robofleet.api.schemas import project as project_schemas
from robofleet.api.schemas.project import SetWorkspaceRequest

if TYPE_CHECKING:
    from pathlib import Path


def test_accepts_path_under_workspaces_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(project_schemas.settings, "workspaces_root", str(tmp_path))
    value = str(tmp_path / "proj-a")

    req = SetWorkspaceRequest(workspace_path=value)

    assert req.workspace_path == value


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "/data/workspaces/../etc/passwd",
        "/data/workspaces/proj/../../etc",
        "bad\x00path",
    ],
)
def test_rejects_empty_traversal_and_nul(
    bad: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(project_schemas.settings, "workspaces_root", "/data/workspaces")
    with pytest.raises(ValidationError):
        SetWorkspaceRequest(workspace_path=bad)


def test_rejects_path_outside_workspaces_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(project_schemas.settings, "workspaces_root", "/data/workspaces")
    with pytest.raises(ValidationError, match="must resolve under"):
        SetWorkspaceRequest(workspace_path="/etc/passwd")


def test_accepts_workspaces_root_itself(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(project_schemas.settings, "workspaces_root", "/data/workspaces")
    req = SetWorkspaceRequest(workspace_path="/data/workspaces")
    assert req.workspace_path == "/data/workspaces"
