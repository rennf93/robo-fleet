"""Structured content columns + quick_context machine-marker split.

Adds four nullable columns to ``tasks``:

- ``pr_reviewer_notes`` (TEXT) — the PR reviewer's own rendered note slot, so a
  review no longer overwrites ``qa_notes`` / ``dev_notes``.
- ``doc_notes`` (TEXT) — the documenter's own rendered note slot (doc content
  used to leak into the human ``quick_context`` blob).
- ``notes_structured`` (JSON) — the typed source of truth for every role's
  structured note (the TEXT note columns become a derived mirror).
- ``orchestration_markers`` (JSON) — the machine markers that used to be packed
  into the human ``quick_context`` blob (``original_developer:<uuid>``,
  ``documenter:<uuid>``, ``required_cells:``, ``external_pr_head=``,
  ``self_heal_fp=``, ``dismissed=1``, ``external_pr_supersede ...``).

``upgrade`` backfills ``orchestration_markers`` from each existing
``quick_context`` and rewrites ``quick_context`` to the human remainder only.
The parse is tolerant — an unrecognised line is kept verbatim as remainder and
never raises. The data step is skipped in offline (``--sql``) mode so the
schema change still renders.

Revision ID: 041_structured_content_columns
Revises: 040_awaiting_pr_review
Create Date: 2026-06-21

NOTE: revision id is 30 chars — alembic's ``alembic_version.version_num`` is
``VARCHAR(32)`` and a longer id raises at record time.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "041_structured_content_columns"
down_revision = "040_awaiting_pr_review"
branch_labels = None
depends_on = None


# Whole-line ``key:value`` markers -> (json key, list-valued?).
_LINE_MARKERS: dict[str, tuple[str, bool]] = {
    "original_developer:": ("original_developer", False),
    "documenter:": ("documenter", False),
    "required_cells:": ("required_cells", True),
    # pr_author was a write-only marker (no reader); park legacy values out of
    # the human quick_context rather than leave them as panel soup.
    "pr_author:": ("pr_author", False),
}
# Whitespace-token ``key=value`` markers (may be space-appended onto a line).
_TOKEN_MARKERS: dict[str, str] = {
    "external_pr_head=": "external_pr_head",
    "self_heal_fp=": "self_heal_fp",
}


def _parse_quick_context(blob: str | None) -> tuple[dict, str | None]:
    """Split a legacy ``quick_context`` into (markers, human remainder).

    Pure + tolerant: any line/token that is not a recognised machine marker is
    preserved as human remainder (``doc_notes:`` is de-prefixed). Never raises.
    """
    markers: dict = {}
    remainder: list[str] = []
    for raw in (blob or "").splitlines():
        line = raw.strip()
        if not line:
            continue

        line_marker = next((p for p in _LINE_MARKERS if line.startswith(p)), None)
        if line_marker is not None:
            key, is_list = _LINE_MARKERS[line_marker]
            val = line[len(line_marker) :].strip()
            markers[key] = (
                [c.strip() for c in val.split(",") if c.strip()] if is_list else val
            )
            continue

        if line.startswith("external_pr_supersede"):
            markers["external_pr_supersede"] = line[
                len("external_pr_supersede") :
            ].strip()
            continue

        if line.startswith("doc_notes:"):
            text = line[len("doc_notes:") :].strip()
            if text:
                remainder.append(text)
            continue

        leftover: list[str] = []
        for tok in line.split():
            if tok == "dismissed=1":
                markers["dismissed"] = True
                continue
            token_marker = next((p for p in _TOKEN_MARKERS if tok.startswith(p)), None)
            if token_marker is not None:
                markers[_TOKEN_MARKERS[token_marker]] = tok[len(token_marker) :]
            else:
                leftover.append(tok)
        if leftover:
            remainder.append(" ".join(leftover))

    return markers, ("\n".join(remainder).strip() or None)


def upgrade() -> None:
    op.add_column("tasks", sa.Column("pr_reviewer_notes", sa.Text(), nullable=True))
    op.add_column("tasks", sa.Column("doc_notes", sa.Text(), nullable=True))
    op.add_column(
        "tasks", sa.Column("notes_structured", postgresql.JSON(), nullable=True)
    )
    op.add_column(
        "tasks", sa.Column("orchestration_markers", postgresql.JSON(), nullable=True)
    )

    # Offline (--sql) mode has no live connection — emit the schema change only.
    if op.get_context().as_sql:
        return

    bind = op.get_bind()
    tasks = sa.table(
        "tasks",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("quick_context", sa.Text()),
        sa.column("orchestration_markers", postgresql.JSON()),
    )
    rows = bind.execute(
        sa.text(
            "SELECT id, quick_context FROM tasks "
            "WHERE quick_context IS NOT NULL AND quick_context <> ''"
        )
    ).fetchall()
    for row in rows:
        markers, remainder = _parse_quick_context(row.quick_context)
        if not markers:
            continue  # nothing machine-y to extract; leave the row untouched
        bind.execute(
            tasks.update()
            .where(tasks.c.id == row.id)
            .values(orchestration_markers=markers, quick_context=remainder)
        )


def downgrade() -> None:
    # Lossy by design: markers are not re-merged back into quick_context.
    op.drop_column("tasks", "orchestration_markers")
    op.drop_column("tasks", "notes_structured")
    op.drop_column("tasks", "doc_notes")
    op.drop_column("tasks", "pr_reviewer_notes")
