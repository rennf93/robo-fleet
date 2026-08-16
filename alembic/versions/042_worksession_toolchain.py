"""WorkSession toolchain columns.

Adds two nullable columns to ``work_sessions`` for agent-runtime toolchain
matching:

- ``toolchain_python`` (VARCHAR(20)) — the Python version the agent's workspace
  was provisioned with (resolved from the target project's ``requires-python``).
- ``toolchain_status`` (VARCHAR(20)) — whether the project's test suite can
  actually be executed in that interpreter: ``ok`` | ``broken`` | ``unknown``.

Pure schema change; no data backfill. Inert until ``ROBOCO_TOOLCHAIN_MATCH_ENABLED``.

Revision ID: 042_worksession_toolchain
Revises: 041_structured_content_columns
Create Date: 2026-06-22

NOTE: revision id is 25 chars — alembic's ``alembic_version.version_num`` is
``VARCHAR(32)`` and a longer id raises at record time.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "042_worksession_toolchain"
down_revision = "041_structured_content_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "work_sessions",
        sa.Column("toolchain_python", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "work_sessions",
        sa.Column("toolchain_status", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("work_sessions", "toolchain_status")
    op.drop_column("work_sessions", "toolchain_python")
