"""Add per-criterion AC ids + child->parent AC linkage to tasks.

Acceptance criteria were a flat ``list[str]`` with no per-criterion identity, so
nothing could relate a child task's criteria back to the parent's. That let a
PM decompose a 16-criterion parent into two children covering half of them, with
the rest silently dropped and never re-checked at roll-up.

This adds two additive array columns:

- ``acceptance_criteria_ids``: a stable id per element of ``acceptance_criteria``
  (1:1, same order). Generated at task creation going forward; backfilled here
  for existing rows as ``md5(task_id || ':' || index)`` so ids are deterministic
  and stable.
- ``parent_ac_refs``: on a child task, the parent AC ids this child is
  responsible for (empty on tasks that are not decomposition children).

Both are nullable-with-default-empty so existing readers are unaffected; the
coverage + roll-up gates that consume them ship in later changes.

Revision ID: 036_ac_ids_and_parent_refs
Revises: 035_secretary_directives
Create Date: 2026-06-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "036_ac_ids_and_parent_refs"
down_revision = "035_secretary_directives"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column(
            "acceptance_criteria_ids",
            sa.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "parent_ac_refs",
            sa.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
    )
    # Backfill stable per-criterion ids for existing rows: md5(task_id:index),
    # one per element of acceptance_criteria, preserving order. Rows with no
    # criteria stay empty.
    op.execute(
        """
        UPDATE tasks
        SET acceptance_criteria_ids = (
            SELECT array_agg(md5(tasks.id::text || ':' || s::text) ORDER BY s)
            FROM generate_subscripts(tasks.acceptance_criteria, 1) AS s
        )
        WHERE acceptance_criteria IS NOT NULL
          AND array_length(acceptance_criteria, 1) > 0
        """
    )


def downgrade() -> None:
    op.drop_column("tasks", "parent_ac_refs")
    op.drop_column("tasks", "acceptance_criteria_ids")
