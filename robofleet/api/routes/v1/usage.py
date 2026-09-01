"""Outbound usage-report endpoint for provider-backed agents.

Provider-backed (Cloud Run Job / ADK_CLOUD_RUN) agents have no ``:9000`` SDK
server to poll, so the agent POSTs its final cumulative counts here and the
orchestrator persists them onto the agent's open ``agent_spawn_sessions``
row. The counts are later read back by
``AgentOrchestrator._resolve_final_token_usage`` at finalize so cost/usage
capture works identically for provider-backed and SDK-polled agents.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header
from sqlalchemy import select, update

from robofleet.api.deps import DbSession
from robofleet.api.routes.v1._role_dep import require_any_authenticated_agent
from robofleet.api.schemas.v1.usage_report import UsageReportRequest
from robofleet.db.tables import AgentSpawnSessionTable
from robofleet.services.repositories import resolve_agent_identity

router = APIRouter(
    prefix="/api/v1/usage",
    tags=["v1-usage"],
    # Token-only guard (same as the do router): any authenticated agent may
    # report usage, regardless of role. The X-Agent-ID is bound to a verified
    # HMAC token by the guard.
    dependencies=[require_any_authenticated_agent],
)

_AgentIdHeader = Annotated[UUID, Header(alias="X-Agent-ID")]


@router.post("/report")
async def report_usage(
    body: UsageReportRequest,
    x_agent_id: _AgentIdHeader,
    db: DbSession,
) -> dict:
    """Persist the agent's final cumulative counts onto its open session row.

    Idempotent: a missing agent, a missing open session, or an unresolved
    UUID all return ``{"status": "ok", "matched": false}`` rather than 500,
    so a provider-backed agent re-POSTing on a transient restart never 500s.
    """
    identity = await resolve_agent_identity(db, str(x_agent_id))
    if identity is None:
        return {"status": "ok", "matched": False}
    _uuid, slug = identity

    result = await db.execute(
        select(AgentSpawnSessionTable.id)
        .where(
            AgentSpawnSessionTable.agent_slug == slug,
            AgentSpawnSessionTable.ended_at.is_(None),
        )
        .order_by(AgentSpawnSessionTable.started_at.desc())
        .limit(1)
    )
    session_id = result.scalar_one_or_none()
    if session_id is None:
        return {"status": "ok", "matched": False}

    await db.execute(
        update(AgentSpawnSessionTable)
        .where(AgentSpawnSessionTable.id == session_id)
        .values(
            turns=body.turns,
            tool_calls=body.tool_calls,
            tokens_input=body.tokens_input,
            tokens_output=body.tokens_output,
            tokens_cache_read=body.tokens_cache_read,
            tokens_cache_write=body.tokens_cache_write,
            exit_reason=body.exit_reason,
        )
    )
    await db.commit()
    return {"status": "ok", "matched": True}
