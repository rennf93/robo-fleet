"""Markdown rendering tests for the structured content models.

Assert structure (labeled sections + the content appears) rather than exact
bytes, so the renderers stay refactorable.
"""

from __future__ import annotations

from roboco.foundation.policy.content import (
    PrReviewContent,
    QaNote,
    ResumptionNote,
    TaskDescription,
)


def test_pr_review_renders_sections_and_findings_table() -> None:
    md = PrReviewContent.model_validate(
        {
            "summary": "The guard is missing on the 422 path.",
            "findings": [
                {
                    "file": "roboco/services/git.py",
                    "line": 42,
                    "severity": "blocker",
                    "expected": "retry as COMMENT",
                    "actual": "raises",
                }
            ],
            "verdict": "changes_requested",
        }
    ).render_markdown()
    assert "## Summary" in md
    assert "## Findings" in md
    assert "| File | Line | Severity | Expected → Actual |" in md
    assert "`roboco/services/git.py`" in md
    assert "blocker" in md
    assert "## Verdict" in md
    assert "changes requested" in md


def test_qa_renders_checklist() -> None:
    md = QaNote.model_validate(
        {
            "summary": "Verified every acceptance criterion against the diff.",
            "ac_verdicts": [
                {
                    "criterion": "AC1 returns 400",
                    "status": "verified",
                    "how": "test passes",
                },
                {"criterion": "AC2 logs", "status": "failed", "how": "no log emitted"},
            ],
            "verdict": "failed",
        }
    ).render_markdown()
    assert "## Acceptance Criteria" in md
    assert "✅" in md and "❌" in md
    assert "AC1 returns 400" in md
    assert "## Verdict" in md


def test_resumption_renders_done_next_where() -> None:
    md = ResumptionNote(
        done="schema module landed",
        next="wire the gateway chokepoint",
        where_to_look=[
            "foundation/policy/content/models.py",
            "services/content_notes.py",
        ],
    ).render_markdown()
    assert "## Done" in md
    assert "## Next" in md
    assert "## Where to look" in md
    assert "content_notes.py" in md
    # No machine markers ever leak into the human resumption note.
    assert "original_developer" not in md
    assert "documenter:" not in md


def test_task_description_renders_all_sections() -> None:
    md = TaskDescription.model_validate(
        {
            "objective": "Add the structured content standard.",
            "what_this_builds": ["a schema layer", "a gateway gate"],
            "the_work": [
                {
                    "team": "backend",
                    "summary": "models + verbs",
                    "items": ["model", "verb"],
                }
            ],
            "notes": ["reuse the Team enum"],
            "acceptance_criteria": ["reviewer notes are isolated"],
        }
    ).render_markdown()
    assert "## Objective" in md
    assert "## What This Builds" in md
    assert "## The Work" in md
    assert "**Backend**" in md
    assert "## Notes" in md
    assert "## Acceptance Criteria" in md
