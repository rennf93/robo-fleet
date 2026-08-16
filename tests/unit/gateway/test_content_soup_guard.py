"""Universal anti-soup guard — no filler/placeholder text in ANY agent field.

``ContentActions._reject_soup`` is applied to every free-text content tool
(say/dm/note/progress/notify/pitch) so soup lands nowhere. It returns a
remediation Envelope (never a raw 422 — that trips the do-server circuit
breaker), or None when the text is substantive.
"""

from __future__ import annotations

import pytest
from roboco.services.gateway.content_actions import ContentActions

_guard = ContentActions._reject_soup


@pytest.mark.parametrize("soup", ["", "   ", "asdf", "...", "wip", "tbd", "x", "-"])
def test_rejects_placeholders_and_filler(soup: str) -> None:
    assert _guard(soup, field="message", min_chars=2) is not None


def test_accepts_substantive_text() -> None:
    assert _guard("LGTM — merging after CI.", field="message", min_chars=2) is None
    assert _guard("ok", field="message", min_chars=2) is None  # terse but real


def test_min_chars_enforced_per_field() -> None:
    # A note must be a sentence, not a fragment.
    assert _guard("hi", field="note", min_chars=8) is not None
    assert _guard("Reviewed the auth refactor.", field="note", min_chars=8) is None


def test_returns_remediation_envelope() -> None:
    env = _guard("asdf", field="progress update", min_chars=5)
    assert env is not None
    assert env.error is not None
    assert "progress update" in (env.remediate or "")
