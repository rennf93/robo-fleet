"""Request schema for the outbound usage-report endpoint.

Provider-backed (Cloud Run Job) agents have no ``:9000`` SDK server to poll,
so the agent POSTs its final cumulative counts to
``POST /api/v1/usage/report`` and the orchestrator persists them onto the
agent's open ``agent_spawn_sessions`` row. The six fields mirror
``TokenUsageStatus`` (roboco/agent_sdk/models.py) one-for-one but live here
in the public API schema layer rather than importing the agent_sdk model, so
the v1 API contract stays decoupled from the in-container SDK.

``exit_reason`` is the provider-backed analogue of the docker exit code: the
ADK entrypoint pushes ``"normal"`` / ``"rate_limited"`` / ``"auth"`` so the
orchestrator's overload break can park the provider without a container exit
code (Cloud Run Jobs expose none). Optional + defaults to None so existing
callers that omit it stay valid.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class UsageReportRequest(BaseModel):
    """Final cumulative usage counts for a provider-backed agent session.

    Counts are absolute (the agent reports its final totals once at end of
    run); the route SETS them on the open spawn-session row, so a re-POST
    with the same values is an idempotent no-op.
    """

    turns: int = Field(
        default=0, description="LLM iterations (unique assistant messages)"
    )
    tool_calls: int = Field(
        default=0, description="Tool invocations accumulated this session"
    )
    tokens_input: int = Field(
        default=0, description="Total input tokens accumulated this session"
    )
    tokens_output: int = Field(
        default=0, description="Total output tokens accumulated this session"
    )
    tokens_cache_read: int = Field(
        default=0, description="Total cache-read tokens this session"
    )
    tokens_cache_write: int = Field(
        default=0, description="Total cache-write tokens this session"
    )
    exit_reason: str | None = Field(
        default=None,
        description=(
            "Provider-backed exit signal: 'normal' | 'rate_limited' | 'auth'. "
            "The orchestrator reads this to park the provider on a rate-limit / "
            "auth failure (no container exit code exists for Cloud Run Jobs)."
        ),
    )
