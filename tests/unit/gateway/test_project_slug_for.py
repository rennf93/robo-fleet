"""``_project_slug_for`` resolves a product-only coordination root's repo.

A normal task carries ``project_id``. A Main-PM coordination root (the only
task a root→master PR ever sits on) often carries just a ``product_id`` (the
cell→repo map) and no project of its own. Before the fallback, the in-path
gate's PR-comment post and the external reviewer's diff fetch both resolved a
``None`` slug and silently no-op'd — so the gate verdict never reached the PR
(observed live: PR #107 / root fead4372 got pr_fail'd with no PR comment).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from roboco.services.gateway.choreographer import Choreographer, ChoreographerDeps


def _make_choreographer() -> Choreographer:
    task = AsyncMock()
    task.session = MagicMock()
    base: dict[str, Any] = {
        "task": task,
        "work_session": AsyncMock(),
        "git": AsyncMock(),
        "a2a": AsyncMock(),
        "journal": AsyncMock(),
        "audit": AsyncMock(),
        "evidence_repo": AsyncMock(),
    }
    return Choreographer(ChoreographerDeps(**base))


@pytest.mark.asyncio
async def test_slug_via_project_id_unchanged() -> None:
    c = _make_choreographer()
    proj = MagicMock(slug="be-proj")
    with patch("roboco.services.project.get_project_service") as gps:
        gps.return_value.get = AsyncMock(return_value=proj)
        slug = await c._project_slug_for(MagicMock(project_id=uuid4(), product_id=None))
    assert slug == "be-proj"


@pytest.mark.asyncio
async def test_slug_falls_back_to_product_when_no_project_id() -> None:
    c = _make_choreographer()
    proj = MagicMock(slug="gca-backend")
    with (
        patch("roboco.services.project.get_project_service") as gps,
        patch("roboco.services.product.get_product_service") as gprod,
    ):
        gps.return_value.get = AsyncMock(return_value=proj)
        gprod.return_value.distinct_project_ids = AsyncMock(return_value=[uuid4()])
        slug = await c._project_slug_for(MagicMock(project_id=None, product_id=uuid4()))
    assert slug == "gca-backend"


@pytest.mark.asyncio
async def test_slug_none_when_no_project_and_no_product() -> None:
    c = _make_choreographer()
    slug = await c._project_slug_for(MagicMock(project_id=None, product_id=None))
    assert slug is None


@pytest.mark.asyncio
async def test_slug_none_when_product_has_no_projects() -> None:
    c = _make_choreographer()
    with patch("roboco.services.product.get_product_service") as gprod:
        gprod.return_value.distinct_project_ids = AsyncMock(return_value=[])
        slug = await c._project_slug_for(MagicMock(project_id=None, product_id=uuid4()))
    assert slug is None
