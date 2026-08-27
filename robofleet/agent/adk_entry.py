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
import re
import sys
import traceback
from pathlib import Path
from typing import Any

import httpx
from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from robofleet.agent.gateway_shim import _base, _load_manifest, build_gateway_tools
from robofleet.agent.git_tools import build_git_tools

_MODEL = os.environ.get("ROBOFLEET_AGENT_MODEL", "gemini-3.5-flash")
_APP_NAME = "robo-fleet"
_SYSTEM_PROMPT_PATH = "/app/system-prompt.md"
# Exit codes mirror the grok/codex/kimi CLIs (75 = rate-limit/quota,
# 78 = auth/credential) so the orchestrator's overload break treats them
# identically across docker and provider-backed agents.
_RATE_LIMIT_EXIT = 75
_AUTH_EXIT = 78


# ADK's inject_session_state treats {var} as a required session-state ref and
# raises KeyError when it's missing. The composed system_prompt carries
# {team}/{project}/{task_id} etc. that compose_prompt leaves as literals
# (harmless under the Claude Code CLI, which does no template substitution,
# but fatal under ADK). {var?} is ADK's optional syntax: a missing var
# substitutes '' instead of raising. Marking every placeholder optional lets
# the orchestrator ship the shared template unfilled and the agent degrade
# cleanly. The proper fix is to fill them at compose time, but that lives in
# the orchestrator (deployable only via a rebuild); this keeps the agent image
# self-sufficient.
_TEMPLATE_VAR_PATTERN = re.compile(r"{+[^{}]*}+")


def _make_optional(template: str) -> str:
    def _sub(m: re.Match[str]) -> str:
        inner = m.group().lstrip("{").rstrip("}").strip()
        if not inner or inner.endswith("?") or inner.startswith("artifact."):
            return m.group()
        return "{" + inner + "?}"

    return _TEMPLATE_VAR_PATTERN.sub(_sub, template)


def _instruction() -> str:
    """Resolve the LlmAgent instruction text.

    Fallback chain: manifest ``system_prompt`` -> /app/system-prompt.md -> "".
    Every ``{var}`` placeholder is marked optional so an unfilled orchestrator
    placeholder degrades to '' under ADK instead of crashing the run.
    """
    manifest = _load_manifest()
    text = manifest.get("system_prompt")
    if isinstance(text, str) and text:
        return _make_optional(text)
    prompt_path = Path(_SYSTEM_PROMPT_PATH)
    if prompt_path.exists():
        return _make_optional(prompt_path.read_text())
    return ""


def _headers() -> dict[str, str]:
    h: dict[str, str] = {
        "X-Agent-ID": os.environ["ROBOFLEET_AGENT_ID"],
        "X-Agent-Role": os.environ["ROBOFLEET_AGENT_ROLE"],
    }
    # The HMAC token is signed over (id, role, team): without the team header
    # the usage POST 401s ("Header values do not match") and the run's tokens
    # never reach the ledger, so spend reads $0 and budget caps never fire.
    team = os.environ.get("ROBOFLEET_AGENT_TEAM", "")
    if team:
        h["X-Agent-Team"] = team
    tok = os.environ.get("ROBOFLEET_AGENT_TOKEN", "")
    if tok and tok != "UNSIGNED":
        h["X-Agent-Token"] = tok
    return h


async def _post_usage(usage: dict[str, Any], exit_reason: str) -> None:
    base = _base()
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


def _log_event(event: Any) -> None:
    """Print a one-line trace of each runner event to stdout for diagnosis."""
    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) or []
    for p in parts:
        if getattr(p, "function_call", None):
            fc = p.function_call
            args = getattr(fc, "args", {}) or {}
            print(
                f"TOOL_CALL name={getattr(fc, 'name', '?')} args={dict(args)}",
                flush=True,
            )
        if getattr(p, "function_response", None):
            fr = p.function_response
            resp = getattr(fr, "response", {}) or {}
            print(
                f"TOOL_RESP name={getattr(fr, 'name', '?')} {str(resp)[:300]}",
                flush=True,
            )
        txt = getattr(p, "text", None)
        if txt:
            print(f"TEXT {str(txt)[:400]}", flush=True)


def _classify(exc: BaseException) -> int | None:
    name = type(exc).__name__
    msg = str(exc)
    if "ResourceExhausted" in name or "429" in msg:
        return _RATE_LIMIT_EXIT
    if "Unauthenticated" in name or "401" in msg:
        return _AUTH_EXIT
    return None


async def _dump_crash(exc: BaseException) -> None:
    """Best-effort: write the crash traceback to GCS so it is readable from a
    host that cannot reach Cloud Logging. Never raises; a write failure is
    swallowed so the real exit path is untouched. The object is overwritten
    each run so the latest crash is what we read.
    """
    bucket = os.environ.get(
        "ROBOFLEET_GCS_BUCKET", "robofleet-deploy-813757481440-state"
    )
    agent = os.environ.get("ROBOFLEET_AGENT_ID", "unknown")
    blob_path = f"diag/crash-{agent}.txt"
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    payload = (
        f"agent={agent} role={os.environ.get('ROBOFLEET_AGENT_ROLE', '?')} "
        f"model={_MODEL}\n\n{tb}\n"
    )
    try:
        import google.cloud.storage  # lazy: only needed on the Cloud Run path

        google.cloud.storage.Client().bucket(bucket).blob(blob_path).upload_from_string(
            payload
        )
    except Exception:
        # The crash dump is diagnostic only; never let it mask the real exit.
        pass


async def _diag(label: str, detail: str = "") -> None:
    """Best-effort GCS heartbeat / status line for a host that cannot reach
    Cloud Logging. Writes one short line to ``diag/run-{agent}.txt``
    (overwritten each run). Paired with _dump_crash: _dump_crash covers
    unclassified exceptions, but the classified exit path (rate_limit/auth)
    returns without a traceback, and an OOM-SIGKILL never reaches either, so
    a STARTED heartbeat is the only signal that main() began at all.
    """
    bucket = os.environ.get(
        "ROBOFLEET_GCS_BUCKET", "robofleet-deploy-813757481440-state"
    )
    agent = os.environ.get("ROBOFLEET_AGENT_ID", "unknown")
    blob_path = f"diag/run-{agent}.txt"
    payload = (
        f"{label} model={_MODEL} role={os.environ.get('ROBOFLEET_AGENT_ROLE', '?')}"
    )
    if detail:
        payload = f"{payload} {detail[:500]}"
    try:
        import google.cloud.storage  # lazy: only needed on the Cloud Run path

        google.cloud.storage.Client().bucket(bucket).blob(blob_path).upload_from_string(
            payload
        )
    except Exception:
        pass


# Consecutive error responses from ONE tool before the run is warned, then cut.
# The Docker path's loop-detector hook has no ADK equivalent, so a model that
# keeps re-issuing a rejected call (a Main PM sent 110 malformed handoff notes
# in one run) would otherwise burn the whole Job timeout plus Cloud Run's
# retries. The cut exits 0 so Cloud Run does NOT retry it; the orchestrator's
# stale-claim reaper releases the task and the respawn breaker bounds re-runs.
_LOOP_WARN_AT = 6
_LOOP_HALT_AT = 12
_loop: dict[str, Any] = {"tool": None, "count": 0}


class ToolLoopError(RuntimeError):
    """One tool rejected the model's call _LOOP_HALT_AT times in a row."""


def _is_error_response(resp: Any) -> bool:
    return isinstance(resp, dict) and bool(
        resp.get("error") or resp.get("status") == "error"
    )


def _on_after_tool(
    tool: Any, args: dict[str, Any], tool_context: Any, tool_response: Any
) -> dict[str, Any] | None:
    """Count consecutive rejections per tool; warn inside the response at
    _LOOP_WARN_AT, raise ToolLoopError at _LOOP_HALT_AT. Any non-error
    response resets the streak."""
    del args, tool_context  # ADK passes them by keyword; the streak ignores them
    name = getattr(tool, "name", "?")
    if not _is_error_response(tool_response):
        _loop["tool"], _loop["count"] = None, 0
        return None
    _loop["count"] = _loop["count"] + 1 if _loop["tool"] == name else 1
    _loop["tool"] = name
    n = _loop["count"]
    if n >= _LOOP_HALT_AT:
        raise ToolLoopError(f"{name} rejected {n} calls in a row")
    if n >= _LOOP_WARN_AT:
        return {
            **tool_response,
            "loop_warning": (
                f"{name} has rejected {n} calls in a row. Do not resend the same"
                " shape: read `message` and `remediate`, change the arguments,"
                " or call i_am_blocked with the reason. The run is cut at"
                f" {_LOOP_HALT_AT}."
            ),
        }
    return None


def _find_cause(exc: BaseException, kind: type[BaseException]) -> bool:
    """True when exc, or anything in its cause/context/`.error` chain, is kind.
    ADK wraps callback exceptions (DynamicNodeFailError carries `.error`)."""
    seen: set[int] = set()
    stack: list[BaseException | None] = [exc]
    while stack:
        e = stack.pop()
        if e is None or id(e) in seen:
            continue
        seen.add(id(e))
        if isinstance(e, kind):
            return True
        stack.extend([e.__cause__, e.__context__, getattr(e, "error", None)])
    return False


def _on_tool_error(
    tool: Any, args: dict[str, Any], tool_context: Any, error: Exception
) -> dict[str, Any] | None:
    """Turn a tool failure into a tool RESPONSE instead of a dead run.

    ADK raises straight out of the runner when the model calls a tool name
    that is not registered (a hallucinated ``robofleet_git_status`` / ``bash``
    killed real Cloud Run executions, which then burned a full container
    restart + re-doing the work on the retry) or when a tool itself raises.
    Handing the error back as the function response lets the model read the
    available-tools list and self-correct in the next turn. A transport
    failure talking to the orchestrator is systemic, not a bad tool name:
    returning None makes ADK re-raise it so the run still dies fast instead
    of the model retrying a dead gateway for many turns.
    """
    if isinstance(error, httpx.HTTPError | ToolLoopError):
        return None
    return {
        "error": type(error).__name__,
        "message": str(error)[:2000],
        "tool": getattr(tool, "name", None),
        "args": args,
        "invocation_id": getattr(tool_context, "invocation_id", None),
        "remediate": "Call one of the registered tools by its exact name.",
    }


async def main() -> int:
    usage = _new_usage()
    # Heartbeat: proves main() began (an OOM-SIGKILL during import leaves no
    # diag/run blob at all, which is itself the OOM signal).
    await _diag("STARTED")
    try:
        instruction = _instruction()
        initial = os.environ.get("ROBOFLEET_INITIAL_PROMPT", "")
        tools: list[Any] = build_gateway_tools() + build_git_tools()
        agent = LlmAgent(
            name="robofleet_agent",
            model=_MODEL,
            instruction=instruction,
            tools=tools,
            on_tool_error_callback=_on_tool_error,
            after_tool_callback=_on_after_tool,
        )
        session_service = InMemorySessionService()
        runner = Runner(
            agent=agent, app_name=_APP_NAME, session_service=session_service
        )
        session = await session_service.create_session(
            app_name=_APP_NAME, user_id="agent"
        )
    except Exception as exc:
        await _dump_crash(exc)
        raise
    await _diag("RUNNER_READY", f"tools={len(agent.tools)}")
    try:
        async for event in runner.run_async(
            user_id="agent",
            session_id=session.id,
            new_message=types.Content(parts=[types.Part(text=initial)]),
        ):
            _accumulate(usage, event)
            _log_event(event)
    except Exception as exc:
        if _find_cause(exc, ToolLoopError):
            await _diag("LOOP_CUT", str(exc)[:300])
            await _post_usage(usage, exit_reason="tool_loop")
            return 0
        code = _classify(exc)
        if code is not None:
            reason = "rate_limited" if code == _RATE_LIMIT_EXIT else "auth"
            # GCS diag BEFORE _post_usage: the usage post can fail (orchestrator
            # unreachable), and this is the only signal for a classified exit
            # since it returns without a _dump_crash traceback.
            await _diag(
                "CLASSIFIED",
                f"exit={code} reason={reason} exc={type(exc).__name__}: {exc}",
            )
            await _post_usage(usage, exit_reason=reason)
            return code
        await _dump_crash(exc)
        raise
    await _post_usage(usage, exit_reason="normal")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
