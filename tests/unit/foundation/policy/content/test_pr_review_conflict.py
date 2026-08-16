"""The PR-review verdict<->findings invariant.

A reviewer's recorded verdict and the GitHub review event both derive from the
``event`` argument, so they must agree with the findings the reviewer cites.
``pr_review_conflict`` is the pure predicate the gateway enforces before any
review is recorded or posted — so an approving review can never be filed (or
posted to a contributor's PR) as a blocking "changes requested", and an
approval can never sail over a blocker.
"""

from __future__ import annotations

from roboco.foundation.policy.content import pr_review_conflict

_BLOCKER = {"file": "a.py", "severity": "blocker", "expected": "x", "actual": "y"}
_MAJOR = {"file": "a.py", "severity": "major", "expected": "x", "actual": "y"}
_MINOR = {"file": "a.py", "severity": "minor", "expected": "x", "actual": "y"}
_NIT = {"file": "a.py", "severity": "nit", "expected": "x", "actual": "y"}


def test_request_changes_with_no_findings_conflicts() -> None:
    # The reported bug: REQUEST_CHANGES (the default) with zero findings — a
    # blocking verdict with nothing cited, contradicting an approving summary.
    conflict = pr_review_conflict("REQUEST_CHANGES", [])
    assert conflict is not None
    message, remediate = conflict
    assert "finding" in message.lower()
    assert "APPROVE" in remediate


def test_request_changes_with_a_finding_is_ok() -> None:
    assert pr_review_conflict("REQUEST_CHANGES", [_MINOR]) is None


def test_approve_over_a_blocker_conflicts() -> None:
    conflict = pr_review_conflict("APPROVE", [_BLOCKER])
    assert conflict is not None
    message, _ = conflict
    assert "approve" in message.lower()


def test_approve_over_a_major_conflicts() -> None:
    assert pr_review_conflict("APPROVE", [_MAJOR]) is not None


def test_approve_with_only_nits_is_ok() -> None:
    assert pr_review_conflict("APPROVE", [_NIT, _MINOR]) is None


def test_approve_with_no_findings_is_ok() -> None:
    assert pr_review_conflict("APPROVE", []) is None


def test_comment_is_never_in_conflict() -> None:
    # A neutral COMMENT carries no verdict, so it is never a contradiction.
    assert pr_review_conflict("COMMENT", []) is None
    assert pr_review_conflict("COMMENT", [_BLOCKER]) is None


def test_findings_none_is_treated_as_empty() -> None:
    assert pr_review_conflict("REQUEST_CHANGES", None) is not None
    assert pr_review_conflict("APPROVE", None) is None


def test_severity_match_is_case_insensitive() -> None:
    upper = {"file": "a.py", "severity": "BLOCKER", "expected": "x", "actual": "y"}
    assert pr_review_conflict("APPROVE", [upper]) is not None
