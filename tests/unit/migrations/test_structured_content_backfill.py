"""Unit tests for migration 041's quick_context -> orchestration_markers parse.

The parse helper is the only logic in the migration that can corrupt prod data,
so it is exercised directly (loaded from the migration file by path — migrations
are not an importable package).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "alembic"
    / "versions"
    / "041_structured_content_columns.py"
)
_spec = importlib.util.spec_from_file_location("_m041", _MIGRATION)
assert _spec and _spec.loader
_m041 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_m041)
parse = _m041._parse_quick_context


def test_none_and_empty() -> None:
    assert parse(None) == ({}, None)
    assert parse("") == ({}, None)
    assert parse("   \n  ") == ({}, None)


def test_original_developer_line_extracted() -> None:
    markers, remainder = parse(
        "original_developer:00000000-0000-0000-0001-000000000002"
    )
    assert markers == {"original_developer": "00000000-0000-0000-0001-000000000002"}
    assert remainder is None


def test_documenter_and_doc_notes_split() -> None:
    blob = (
        "original_developer:dev-uuid\n\n"
        "doc_notes:Created backend/docs/cache-and-locks.md documenting prefixes\n"
        "documenter:doc-uuid"
    )
    markers, remainder = parse(blob)
    assert markers["original_developer"] == "dev-uuid"
    assert markers["documenter"] == "doc-uuid"
    # The human doc note survives, de-prefixed; the UUIDs do NOT leak into it.
    assert remainder == "Created backend/docs/cache-and-locks.md documenting prefixes"
    assert "documenter" not in remainder
    assert "original_developer" not in remainder


def test_required_cells_list() -> None:
    markers, remainder = parse("required_cells: backend, frontend, ux_ui")
    assert markers == {"required_cells": ["backend", "frontend", "ux_ui"]}
    assert remainder is None


def test_token_markers_and_dismissed_on_one_line() -> None:
    markers, remainder = parse("external_pr_head=abc123 dismissed=1")
    assert markers == {"external_pr_head": "abc123", "dismissed": True}
    assert remainder is None


def test_self_heal_fp_token() -> None:
    markers, _ = parse("self_heal_fp=deadbeef")
    assert markers == {"self_heal_fp": "deadbeef"}


def test_supersede_line_preserved() -> None:
    markers, remainder = parse("external_pr_supersede pr=123 review=rid closed=1")
    assert markers == {"external_pr_supersede": "pr=123 review=rid closed=1"}
    assert remainder is None


def test_malformed_blob_kept_as_remainder_never_raises() -> None:
    markers, remainder = parse(":::garbage\nsome free text a human wrote")
    assert markers == {}
    assert ":::garbage" in remainder
    assert "some free text a human wrote" in remainder


def test_dismissed_appended_to_human_text() -> None:
    # dismissed=1 is space-appended (services/task.py): the human text survives,
    # the marker is extracted.
    markers, remainder = parse("kept some human note dismissed=1")
    assert markers == {"dismissed": True}
    assert remainder == "kept some human note"
