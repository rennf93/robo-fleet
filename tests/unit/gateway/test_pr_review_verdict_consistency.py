"""post_pr_review refuses a self-contradicting verdict before it is recorded/posted.

The recorded ``notes_structured.pr_review.verdict`` and the GitHub review event
both derive from the verb's ``event`` argument. A reviewer who concludes
"approve" in the body but leaves ``event`` at its ``REQUEST_CHANGES`` default
(with no findings) would otherwise file — and post to the contributor's PR — a
blocking "changes requested" that contradicts the approving summary. The gate
catches that at the choreographer before any side effect runs.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from roboco.services.gateway.choreographer import Choreographer, ChoreographerDeps


def _make_choreographer() -> Choreographer:
    base: dict[str, Any] = {
        "task": AsyncMock(),
        "work_session": AsyncMock(),
        "git": AsyncMock(),
        "a2a": AsyncMock(),
        "journal": AsyncMock(),
        "audit": AsyncMock(),
        "evidence_repo": AsyncMock(),
    }
    return Choreographer(ChoreographerDeps(**base))


_CLEAN_FINDING = {
    "file": "a.py",
    "severity": "minor",
    "expected": "x",
    "actual": "y",
}
_BLOCKER = {"file": "a.py", "severity": "blocker", "expected": "x", "actual": "y"}


@pytest.mark.asyncio
async def test_request_changes_without_findings_is_rejected() -> None:
    c = _make_choreographer()
    env = await c._verdict_consistency_gate(
        MagicMock(),
        uuid4(),
        uuid4(),
        "pr_reviewer",
        {},
        event="REQUEST_CHANGES",
        findings=[],
    )
    assert env is not None
    body = env.as_dict()
    assert body["error"] == "invalid_state"
    assert "finding" in body["message"].lower()


@pytest.mark.asyncio
async def test_approve_over_a_blocker_is_rejected() -> None:
    c = _make_choreographer()
    env = await c._verdict_consistency_gate(
        MagicMock(),
        uuid4(),
        uuid4(),
        "pr_reviewer",
        {},
        event="APPROVE",
        findings=[_BLOCKER],
    )
    assert env is not None
    assert env.as_dict()["error"] == "invalid_state"


@pytest.mark.asyncio
async def test_request_changes_with_findings_passes_gate() -> None:
    c = _make_choreographer()
    env = await c._verdict_consistency_gate(
        MagicMock(),
        uuid4(),
        uuid4(),
        "pr_reviewer",
        {},
        event="REQUEST_CHANGES",
        findings=[_CLEAN_FINDING],
    )
    assert env is None


@pytest.mark.asyncio
async def test_clean_approve_passes_gate() -> None:
    c = _make_choreographer()
    env = await c._verdict_consistency_gate(
        MagicMock(),
        uuid4(),
        uuid4(),
        "pr_reviewer",
        {},
        event="APPROVE",
        findings=[],
    )
    assert env is None
