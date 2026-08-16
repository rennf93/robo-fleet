"""required_cells decomposition gate — marker parse + uncovered-cell coverage.

The Main PM must create a subtask for each cell the brief explicitly names
(recorded as a ``required_cells`` orchestration marker on the parent). The gate
is inert when no marker is present, so legacy decompositions never block.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from roboco.services.task import TaskService, extract_required_cells


def _task(required_cells: list[str] | None = None) -> SimpleNamespace:
    om = {"required_cells": required_cells} if required_cells is not None else None
    return SimpleNamespace(orchestration_markers=om)


# ---------------------------------------------------------------------------
# extract_required_cells (marker reader)
# ---------------------------------------------------------------------------


def test_extract_required_cells_absent_is_empty() -> None:
    assert extract_required_cells(_task()) == []
    assert (
        extract_required_cells(
            SimpleNamespace(orchestration_markers={"original_developer": "abc"})
        )
        == []
    )


def test_extract_required_cells_normalizes() -> None:
    assert extract_required_cells(_task(["Backend", "Frontend ", "UX/UI"])) == [
        "backend",
        "frontend",
        "ux_ui",
    ]


def test_extract_required_cells_dedups_in_order() -> None:
    assert extract_required_cells(_task(["backend", "backend", "frontend"])) == [
        "backend",
        "frontend",
    ]


# ---------------------------------------------------------------------------
# uncovered_required_cells (service coverage check)
# ---------------------------------------------------------------------------


def _service(
    required_cells: list[str] | None, child_teams: list[str | None]
) -> TaskService:
    """A TaskService whose get()/get_subtasks() return a parent + these children."""
    svc = TaskService(MagicMock())
    parent = _task(required_cells)
    children = [MagicMock(team=t) for t in child_teams]
    object.__setattr__(svc, "get", AsyncMock(return_value=parent))
    object.__setattr__(svc, "get_subtasks", AsyncMock(return_value=children))
    return svc


@pytest.mark.asyncio
async def test_uncovered_inert_without_marker() -> None:
    svc = _service(None, ["backend"])
    assert await svc.uncovered_required_cells(uuid4()) == []


@pytest.mark.asyncio
async def test_uncovered_flags_the_dropped_cell() -> None:
    # Brief named backend+frontend+ux_ui; only backend+frontend got subtasks.
    svc = _service(["backend", "frontend", "ux_ui"], ["backend", "frontend"])
    assert await svc.uncovered_required_cells(uuid4()) == ["ux_ui"]


@pytest.mark.asyncio
async def test_uncovered_empty_when_all_named_cells_covered() -> None:
    svc = _service(["backend", "frontend"], ["frontend", "backend"])
    assert await svc.uncovered_required_cells(uuid4()) == []


@pytest.mark.asyncio
async def test_uncovered_normalizes_child_team_form() -> None:
    # Marker uses underscore, child team uses the slash form — they match.
    svc = _service(["ux_ui"], ["UX/UI"])
    assert await svc.uncovered_required_cells(uuid4()) == []
