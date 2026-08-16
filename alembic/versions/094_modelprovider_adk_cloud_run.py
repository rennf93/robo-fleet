"""Add 'adk_cloud_run' to the postgres modelprovider enum.

ADK_CLOUD_RUN (``ModelProvider.ADK_CLOUD_RUN``) is the new agent backend for
the Google Cloud port: agents run as one-shot Cloud Run Jobs executing a
Google ADK Runner on Gemini, spawned through ``CloudRunJobsProvider`` instead
of the docker CLI path. Routing agents to it requires the postgres
``modelprovider`` enum to carry the value. Mirrors the enum-add pattern of
migration 090 (kimi); no provider-row seed is needed because ADK agents are
assigned the backend via ``OrchestratorAgentConfig.provider_type`` rather than
a seeded providers-table row.

Revision ID: 094_modelprovider_adk_cloud_run
Revises: 093_playbook_source_program
Create Date: 2026-08-16
"""

from __future__ import annotations

from alembic import op

revision = "094_modelprovider_adk_cloud_run"
down_revision = "093_playbook_source_program"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # alembic runs the whole upgrade in a single transaction, and Postgres
    # forbids using a freshly added enum value in the same transaction that
    # added it (UnsafeNewEnumValueUsageError). autocommit_block commits the
    # ALTER on its own. Still renders the ALTER TYPE in offline --sql, so the
    # enum-migration-parity test sees it. Idempotent via IF NOT EXISTS.
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE modelprovider ADD VALUE IF NOT EXISTS 'adk_cloud_run'"
        )


def downgrade() -> None:
    # Postgres does not support removing enum values without a destructive
    # type recreation. Forward-only by design (see migration 037).
    pass