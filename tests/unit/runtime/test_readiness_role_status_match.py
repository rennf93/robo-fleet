"""Smoke-8: _readiness_check_role_for_status covers dev-owned states.

Original gap: the role-mismatch table only mapped handoff states
(awaiting_qa, awaiting_documentation, awaiting_pm_review,
awaiting_ceo_approval) to required roles. needs_revision/verifying had
no entry, so a QA spawn for a needs_revision task passed the readiness
check and the gateway rejected claim_review afterwards. Defense in depth
layered behind the _check_health fix.
"""

from __future__ import annotations

from roboco.runtime.orchestrator import AgentOrchestrator


def test_qa_on_needs_revision_blocked() -> None:
    """QA cannot be spawned for a needs_revision task."""
    reason = AgentOrchestrator._readiness_check_role_for_status(
        agent_id="be-qa", role="qa", status="needs_revision"
    )
    assert reason is not None
    assert "needs_revision" in reason
    assert "qa" in reason


def test_pm_on_needs_revision_blocked() -> None:
    """PM cannot be spawned for a needs_revision task either."""
    reason = AgentOrchestrator._readiness_check_role_for_status(
        agent_id="be-pm", role="cell_pm", status="needs_revision"
    )
    assert reason is not None


def test_developer_on_needs_revision_allowed() -> None:
    """Developer (and documenter) ARE the right roles for needs_revision."""
    reason = AgentOrchestrator._readiness_check_role_for_status(
        agent_id="be-dev-1", role="developer", status="needs_revision"
    )
    assert reason is None


def test_documenter_on_needs_revision_allowed() -> None:
    """Documenter can rework — same dev/doc-owned set."""
    reason = AgentOrchestrator._readiness_check_role_for_status(
        agent_id="be-doc", role="documenter", status="needs_revision"
    )
    assert reason is None


def test_qa_on_verifying_blocked() -> None:
    """Verifying belongs to the dev/doc roles, not QA."""
    reason = AgentOrchestrator._readiness_check_role_for_status(
        agent_id="be-qa", role="qa", status="verifying"
    )
    assert reason is not None


def test_qa_on_awaiting_qa_allowed() -> None:
    """The original handoff case still works — QA on awaiting_qa is fine."""
    reason = AgentOrchestrator._readiness_check_role_for_status(
        agent_id="be-qa", role="qa", status="awaiting_qa"
    )
    assert reason is None


def test_unmapped_status_allows_any_role() -> None:
    """Statuses with no role lock (pending, paused, blocked, etc.) pass."""
    for status in ("pending", "claimed", "in_progress", "paused", "blocked"):
        for role in ("developer", "qa", "documenter", "cell_pm"):
            assert (
                AgentOrchestrator._readiness_check_role_for_status(
                    agent_id="x", role=role, status=status
                )
                is None
            ), f"role={role} status={status} should not be rejected by this gate"


# ---------------------------------------------------------------------------
# Coordination roots — a CEO-rejected coordination root returns to its PM (#5).
# ---------------------------------------------------------------------------


def test_pm_on_needs_revision_coordination_allowed() -> None:
    """A coordination root in needs_revision belongs to its PM, not a dev."""
    for role in ("main_pm", "cell_pm"):
        assert (
            AgentOrchestrator._readiness_check_role_for_status(
                agent_id="main-pm",
                role=role,
                status="needs_revision",
                is_coordination=True,
            )
            is None
        )


def test_pm_on_verifying_coordination_allowed() -> None:
    assert (
        AgentOrchestrator._readiness_check_role_for_status(
            agent_id="main-pm", role="main_pm", status="verifying", is_coordination=True
        )
        is None
    )


def test_dev_on_needs_revision_coordination_still_allowed() -> None:
    """Widening is additive — developer is still accepted."""
    assert (
        AgentOrchestrator._readiness_check_role_for_status(
            agent_id="be-dev-1",
            role="developer",
            status="needs_revision",
            is_coordination=True,
        )
        is None
    )


def test_qa_on_needs_revision_coordination_still_blocked() -> None:
    """The widening only adds the PM roles — QA is still a misroute."""
    reason = AgentOrchestrator._readiness_check_role_for_status(
        agent_id="be-qa", role="qa", status="needs_revision", is_coordination=True
    )
    assert reason is not None


def test_pm_on_needs_revision_noncoordination_still_blocked() -> None:
    """A normal (code) needs_revision task is still dev/doc-only for a PM when it
    is NOT PM-owned (owner_is_pm unset) — the raw default behaviour."""
    reason = AgentOrchestrator._readiness_check_role_for_status(
        agent_id="be-pm", role="cell_pm", status="needs_revision", is_coordination=False
    )
    assert reason is not None


# ---------------------------------------------------------------------------
# Gate-failed assembled PRs — the PR-review gate's pr_fail sends a cell->root /
# root->master PR back to needs_revision, still owned by the PM. It is NOT a
# coordination task (it has a project + branch), so the readiness waiver relies
# on owner_is_pm (mirroring _dispatch_revision_coordination_roots). Regression
# for the production deadlock: "spawn refused for be-pm ... state=needs_revision
# requires role in {'documenter','developer'} but agent be-pm is 'cell_pm'".
# ---------------------------------------------------------------------------


def test_pm_on_needs_revision_owner_is_pm_allowed() -> None:
    """A gate-failed assembled PR is PM-owned but NOT coordination; the owning
    cell/main PM must be spawnable to revise it."""
    for role in ("main_pm", "cell_pm"):
        assert (
            AgentOrchestrator._readiness_check_role_for_status(
                agent_id="be-pm", role=role, status="needs_revision", owner_is_pm=True
            )
            is None
        )


def test_pm_on_verifying_owner_is_pm_allowed() -> None:
    assert (
        AgentOrchestrator._readiness_check_role_for_status(
            agent_id="be-pm", role="cell_pm", status="verifying", owner_is_pm=True
        )
        is None
    )


def test_qa_on_needs_revision_owner_is_pm_still_blocked() -> None:
    """owner_is_pm widens to the PM roles only — QA is still a misroute."""
    reason = AgentOrchestrator._readiness_check_role_for_status(
        agent_id="be-qa", role="qa", status="needs_revision", owner_is_pm=True
    )
    assert reason is not None
