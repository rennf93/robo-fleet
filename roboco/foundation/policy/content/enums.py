"""Enumerations for structured agent content.

These are the controlled vocabularies the content schema models
(:mod:`roboco.foundation.policy.content.models`) validate against. The cell
``Team`` vocabulary is reused from :mod:`roboco.foundation.identity` rather
than redefined here.
"""

from __future__ import annotations

from enum import StrEnum


class Severity(StrEnum):
    """Severity ladder for a PR-review finding (worst → least)."""

    BLOCKER = "blocker"  # must fix before merge
    MAJOR = "major"  # significant defect
    MINOR = "minor"  # small defect, fix advised
    NIT = "nit"  # cosmetic / preference


class Verdict(StrEnum):
    """Outcome of a review.

    ``approved`` / ``changes_requested`` describe a PR review; ``passed`` /
    ``failed`` describe a QA or in-path gate review. All four are valid
    ``PrReviewContent`` verdicts; ``QaNote`` accepts only ``passed`` /
    ``failed``.
    """

    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    PASSED = "passed"
    FAILED = "failed"
