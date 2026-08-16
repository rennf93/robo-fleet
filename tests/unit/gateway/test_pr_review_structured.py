"""post_pr_review structured-findings helper.

The reviewer supplies a summary + structured findings; the verb generates the
canonical GitHub comment from them and rejects malformed findings.
"""

from __future__ import annotations

from roboco.foundation.policy.content import PrReviewContent
from roboco.services.gateway.choreographer.pr_review import PRReviewerMixin
from roboco.services.gateway.envelope import Envelope

_build = PRReviewerMixin._build_pr_review_content


def test_valid_findings_build_pr_review_content() -> None:
    content = _build(
        "The 422 path is unguarded.",
        [
            {
                "file": "roboco/services/git.py",
                "line": 42,
                "severity": "blocker",
                "expected": "retry as COMMENT",
                "actual": "raises",
            }
        ],
        "REQUEST_CHANGES",
    )
    assert isinstance(content, PrReviewContent)
    assert content.verdict.value == "changes_requested"
    md = content.render_markdown()
    assert "## Findings" in md
    assert "`roboco/services/git.py`" in md
    assert "blocker" in md


def test_approve_event_maps_to_approved_verdict() -> None:
    content = _build("All criteria met; clean diff.", [], "APPROVE")
    assert isinstance(content, PrReviewContent)
    assert content.verdict.value == "approved"


def test_malformed_findings_return_envelope() -> None:
    # A finding missing the required `actual` field is rejected with remediation.
    result = _build(
        "Something is off here.",
        [{"file": "a.py", "severity": "minor", "expected": "x"}],
        "REQUEST_CHANGES",
    )
    assert isinstance(result, Envelope)
    assert result.error is not None
    assert "finding" in (result.remediate or "").lower()
