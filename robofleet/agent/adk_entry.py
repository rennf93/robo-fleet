"""ADK agent entrypoint: build the LlmAgent, run to completion, report usage.

The agent runs as a one-shot process: compose the LlmAgent with the gateway
tool-shim + git/file FunctionTools, run it over an InMemorySessionService
session on Gemini 3.5 Flash, accumulate token counts from each event's
``usage_metadata``, POST the final totals to ``/api/v1/usage/report``, and map
provider errors to exit codes (75 = ResourceExhausted/quota, 78 =
Unauthenticated) mirroring the grok/codex/kimi conventions.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from robofleet.agent.gateway_shim import _load_manifest, build_gateway_tools
from robofleet.agent.git_tools import build_git_tools

_MODEL = os.environ.get("ROBOCO_AGENT_MODEL", "gemini-3.5-flash")
_APP_NAME = "robo-fleet"
_SYSTEM_PROMPT_PATH = "/app/system-prompt.md"
# Exit codes mirror the grok/codex/kimi CLIs (75 = rate-limit/quota,
# 78 = auth/credential) so the orchestrator's overload break treats them
# identically across docker and provider-backed agents.
_RATE_LIMIT_EXIT = 75
_AUTH_EXIT = 78


def _instruction() -> str:
    """Resolve the LlmAgent instruction text.

    Fallback chain: manifest ``system_prompt`` -> /app/system-prompt.md -> "".
    """
    manifest = _load_manifest()
    text = manifest.get("system_prompt")
    if isinstance(text, str) and text:
        return text
    prompt_path = Path(_SYSTEM_PROMPT_PATH)
    if prompt_path.exists():
        return prompt_path.read_text()
    return ""


def _headers() -> dict[str, str]:
    h: dict[str, str] = {
        "X-Agent-ID": os.environ["ROBOCO_AGENT_ID"],
        "X-Agent-Role": os.environ["ROBOCO_AGENT_ROLE"],
    }
    tok = os.environ.get("ROBOCO_AGENT_TOKEN", "")
    if tok and tok != "UNSIGNED":
        h["X-Agent-Token"] = tok
    return h


async def _post_usage(usage: dict[str, Any], exit_reason: str) -> None:
    base = os.environ.get("ROBOCO_ORCHESTRATOR_URL", "http://roboco-orchestrator:8000")
    payload = {**usage, "exit_reason": exit_reason}
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(
            f"{base}/api/v1/usage/report", json=payload, headers=_headers()
        )


def _new_usage() -> dict[str, Any]:
    return {
        "turns": 0,
        "tool_calls": 0,
        "tokens_input": 0,
        "tokens_output": 0,
        "tokens_cache_read": 0,
        "tokens_cache_write": 0,
    }


def _accumulate(usage: dict[str, Any], event: Any) -> None:
    usage["turns"] += 1
    u = getattr(event, "usage_metadata", None)
    if u is not None:
        usage["tokens_input"] = getattr(u, "prompt_token_count", 0) or 0
        usage["tokens_output"] = getattr(u, "candidates_token_count", 0) or 0
        # cached_content_token_count is the genai cache-read field; cache-write
        # has no clean summary scalar, left at 0.
        usage["tokens_cache_read"] = getattr(u, "cached_content_token_count", 0) or 0


def _classify(exc: BaseException) -> int | None:
    name = type(exc).__name__
    msg = str(exc)
    if "ResourceExhausted" in name or "429" in msg:
        return _RATE_LIMIT_EXIT
    if "Unauthenticated" in name or "401" in msg:
        return _AUTH_EXIT
    return None


async def main() -> int:
    instruction = _instruction()
    initial = os.environ.get("ROBOCO_INITIAL_PROMPT", "")
    tools: list[Any] = build_gateway_tools() + build_git_tools()
    agent = LlmAgent(
        name="roboco_agent",
        model=_MODEL,
        instruction=instruction,
        tools=tools,
    )
    session_service = InMemorySessionService()
    runner = Runner(agent=agent, app_name=_APP_NAME, session_service=session_service)
    session = await session_service.create_session(app_name=_APP_NAME, user_id="agent")
    usage = _new_usage()
    try:
        async for event in runner.run_async(
            user_id="agent",
            session_id=session.id,
            new_message=types.Content(parts=[types.Part(text=initial)]),
        ):
            _accumulate(usage, event)
    except Exception as exc:
        code = _classify(exc)
        if code is not None:
            reason = "rate_limited" if code == _RATE_LIMIT_EXIT else "auth"
            await _post_usage(usage, exit_reason=reason)
            return code
        raise
    await _post_usage(usage, exit_reason="normal")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
