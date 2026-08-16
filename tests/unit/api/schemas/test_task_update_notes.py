"""The note fields are first-class on the task update + response schemas."""

from __future__ import annotations

from roboco.api.schemas.tasks import TaskResponse
from roboco.api.schemas.tasks import TaskUpdate as ApiTaskUpdate
from roboco.models.task import TaskUpdate as DomainTaskUpdate


def test_api_task_update_accepts_auditor_and_pr_reviewer_notes() -> None:
    u = ApiTaskUpdate(
        auditor_notes="audit", pr_reviewer_notes="review", doc_notes="doc"
    )
    assert u.auditor_notes == "audit"
    assert u.pr_reviewer_notes == "review"
    assert u.doc_notes == "doc"


def test_domain_task_update_accepts_new_notes() -> None:
    u = DomainTaskUpdate(
        auditor_notes="audit", pr_reviewer_notes="review", doc_notes="doc"
    )
    assert u.auditor_notes == "audit"
    assert u.pr_reviewer_notes == "review"
    assert u.doc_notes == "doc"


def test_task_response_exposes_structured_fields() -> None:
    fields = set(TaskResponse.model_fields)
    assert {
        "pr_reviewer_notes",
        "doc_notes",
        "notes_structured",
        "orchestration_markers",
    } <= fields
