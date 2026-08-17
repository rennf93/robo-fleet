"""Gemini/ADK interactive session - the IntakeSession seam for the GCP port.

The Claude interactive roles (intake/secretary) ran a held-open
``ClaudeSDKClient``; the grok path runs per-turn headless ``grok -p``. This is
the Gemini/ADK twin: one persistent ADK ``InMemorySessionService`` session +
``Runner`` over an ``LlmAgent`` (model ``gemini-3.5-flash``), with the role's
MCP tool server wired as an ADK ``McpToolset`` (stdio subprocess). The
``IntakeDriver`` loop, message source, and relay are reused unchanged from
the shared transport - only the ``SessionFactory`` differs, exactly like the
grok path.

Draft/batch delivery mirrors the grok path: the ``robofleet-intake`` MCP
server POSTs the draft/batch to the relay directly (tool-call results do not
need to be intercepted here). A fenced ``robofleet-draft`` text fallback is
surfaced via ``_extract_draft`` (shared with grok) for the case where the
agent types the spec instead of calling the tool.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import structlog
from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import McpToolset
from google.genai import types
from mcp import StdioServerParameters

from robofleet.agent_sdk.intake_driver import StreamChunk, _extract_draft

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = structlog.get_logger()

_MODEL = os.environ.get("ROBOFLEET_AGENT_MODEL", "gemini-3.5-flash")
_APP_NAME = "robo-fleet"

# Env forwarded into the MCP subprocess so the tool server authenticates to the
# orchestrator (same env the grok config forwards into its MCP server).
_MCP_ENV_KEYS: tuple[str, ...] = (
    "ROBOFLEET_API_URL",
    "ROBOFLEET_ORCHESTRATOR_URL",
    "ROBOFLEET_AGENT_TOKEN",
    "ROBOFLEET_AGENT_ID",
    "ROBOFLEET_AGENT_ROLE",
    "ROBOFLEET_PROMPTER_SESSION_ID",
    "ROBOFLEET_SECRETARY_SESSION_ID",
)


def _mcp_subprocess_env() -> dict[str, str]:
    """Build the env for the MCP server subprocess from the container's env."""
    env: dict[str, str] = {"UV_PROJECT_ENVIRONMENT": "/app/.venv"}
    for key in _MCP_ENV_KEYS:
        val = os.environ.get(key)
        if val:
            env[key] = val
    return env


# ---------------------------------------------------------------------------
# ADK Event -> StreamChunk conversion (pure, unit-tested with fakes).
# ---------------------------------------------------------------------------


def _part_to_chunk(part: Any, text_acc: list[str]) -> StreamChunk | None:
    """Map one genai Part to a chunk, appending text for the draft fallback.

    ``text_acc`` accumulates the turn's text so the caller can mine it for a
    fenced draft (the fallback path) at turn end.
    """
    # A thought/thinking part (Gemini "thought" summaries).
    text = getattr(part, "text", None)
    is_thought = bool(getattr(part, "thought", False))
    if isinstance(text, str) and text:
        text_acc.append(text)
        return StreamChunk(kind="thinking", text=text) if is_thought else None
    fc = getattr(part, "function_call", None)
    if fc is not None:
        name = getattr(fc, "name", "") or ""
        args = getattr(fc, "args", None) or {}
        return StreamChunk(kind="tool_use", tool=name, data={"args": args})
    return None


def _event_to_chunks(event: Any, text_acc: list[str]) -> list[StreamChunk]:
    """Map one ADK Event to zero or more StreamChunks.

    Error events yield an ``error`` chunk; a turn-complete event yields a
    ``turn_end`` chunk (plus a fenced-draft fallback mined from the
    accumulated text). Content parts are mapped via ``_part_to_chunk``.
    """
    chunks: list[StreamChunk] = []
    err_code = getattr(event, "error_code", None)
    if err_code:
        msg = getattr(event, "error_message", "") or err_code
        chunks.append(StreamChunk(kind="error", text=str(msg)))
        return chunks
    content = getattr(event, "content", None)
    if content is not None:
        for part in getattr(content, "parts", None) or []:
            chunk = _part_to_chunk(part, text_acc)
            if chunk is not None:
                chunks.append(chunk)
    if getattr(event, "turn_complete", False):
        draft = _extract_draft("".join(text_acc))
        if draft is not None:
            chunks.append(StreamChunk(kind="draft", data=draft))
        chunks.append(StreamChunk(kind="turn_end", data={}))
    return chunks


class GeminiChatSession:  # pragma: no cover - needs the live container + API key
    """``IntakeSession`` backed by a persistent ADK Runner over Gemini.

    Async context manager: ``__aenter__`` builds the McpToolset, LlmAgent,
    session service, session, and Runner; ``__aexit__`` closes the toolset.
    ``send`` runs one turn via ``runner.run_async`` and yields StreamChunks.
    Conversation context persists in the single ADK session across turns.
    """

    def __init__(self, *, server_module: str, system_prompt: str) -> None:
        self._server_module = server_module
        self._system_prompt = system_prompt
        self._toolset: McpToolset | None = None
        self._runner: Runner | None = None
        self._session: Any = None
        self._session_service: InMemorySessionService | None = None

    async def __aenter__(self) -> GeminiChatSession:
        self._toolset = McpToolset(
            connection_params=StdioServerParameters(
                command="uv",
                args=[
                    "run",
                    "--directory",
                    "/app",
                    "--no-sync",
                    "python",
                    "-m",
                    f"robofleet.mcp.{self._server_module}",
                ],
                env=_mcp_subprocess_env(),
            ),
        )
        agent = LlmAgent(
            name=f"robofleet_{self._server_module}",
            model=_MODEL,
            instruction=self._system_prompt,
            tools=[self._toolset],
        )
        self._session_service = InMemorySessionService()
        self._session = await self._session_service.create_session(
            app_name=_APP_NAME, user_id="agent"
        )
        self._runner = Runner(
            agent=agent,
            app_name=_APP_NAME,
            session_service=self._session_service,
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._toolset is not None:
            await self._toolset.close()

    async def send(self, text: str) -> AsyncIterator[StreamChunk]:
        """Run one turn and yield its chunks; always ends with turn_end."""
        if not os.environ.get("GEMINI_API_KEY"):
            yield StreamChunk(
                kind="error",
                text=(
                    "GEMINI_API_KEY is not set - the Gemini interactive session "
                    "cannot call the model. Set the key in the container env."
                ),
            )
            yield StreamChunk(kind="turn_end", data={})
            return
        assert self._runner is not None
        assert self._session is not None
        text_acc: list[str] = []
        try:
            async for event in self._runner.run_async(
                user_id="agent",
                session_id=self._session.id,
                new_message=types.Content(parts=[types.Part(text=text)], role="user"),
            ):
                for chunk in _event_to_chunks(event, text_acc):
                    yield chunk
        except Exception as exc:
            logger.error("Gemini turn failed", error=str(exc))
            yield StreamChunk(kind="error", text=str(exc))
            yield StreamChunk(kind="turn_end", data={})
