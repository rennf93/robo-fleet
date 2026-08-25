"""ADK tool shim: maps role flow/do verbs to orchestrator HTTP routes.

The agent process talks to the existing orchestrator gateway over HTTP instead
of MCP servers. Flow verbs POST to ``{base}/api/v1/flow/{segment}/{verb}`` where
``segment`` is ``"board"`` for product_owner/head_marketing, else the role
string. Do tools POST to ``{base}/api/v1/do/{tool}``. The intent->public verb
remap (``pass_review``->``pass``, ``fail_review``->``fail``) mirrors the route
registration in ``robofleet/api/routes/v1/flow_qa.py``; the PR-gate verbs
``pr_pass``/``pr_fail`` are already public route names and need no remap.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, cast

import httpx
from google.adk.tools import FunctionTool
from urllib.parse import urlparse

# product_owner/head_marketing share the /flow/board segment (flow_board.py).
_BOARD_ROLES = {"product_owner", "head_marketing"}
# Intent verbs (manifest) -> public route names. Confirmed against flow_qa.py:
# /pass and /fail are the registered routes; pass_review/fail_review are the
# intent-verb names emitted by lifecycle.intents_for_role(Role.QA).
_INTENT_TO_PUBLIC: dict[str, str] = {"pass_review": "pass", "fail_review": "fail"}

_DEFAULT_BASE = "http://robofleet-orchestrator:8000"
_DEFAULT_MANIFEST = "/app/tool-manifest.json"
# Public orchestrator URL used when the injected ROBOFLEET_ORCHESTRATOR_URL is
# non-routable from a Cloud Run Job. The orchestrator deploys without
# ROBOFLEET_API_URL set, so the provider's _resolve_api_url falls back to a
# loopback/mesh address (127.0.0.1 / robofleet-orchestrator:8000) that a Cloud
# Run Job container cannot reach (it is not on the docker mesh). Overridable
# via ROBOFLEET_PUBLIC_API_URL so a non-default deploy does not bake in.
_PUBLIC_FALLBACK = os.environ.get(
    "ROBOFLEET_PUBLIC_API_URL",
    "https://robofleet-orchestrator-813757481440.us-central1.run.app",
)


def _non_routable(base: str) -> bool:
    host = (urlparse(base).hostname or "").lower()
    return host in ("localhost", "robofleet-orchestrator") or host.startswith("127.")


def _base() -> str:
    base = os.environ.get("ROBOFLEET_ORCHESTRATOR_URL", _DEFAULT_BASE)
    return _PUBLIC_FALLBACK if _non_routable(base) else base


def _segment() -> str:
    role = os.environ.get("ROBOFLEET_AGENT_ROLE", "")
    return "board" if role in _BOARD_ROLES else role


def _headers() -> dict[str, str]:
    h: dict[str, str] = {
        "X-Agent-ID": os.environ.get("ROBOFLEET_AGENT_ID", ""),
        "X-Agent-Role": os.environ.get("ROBOFLEET_AGENT_ROLE", ""),
        "X-Correlation-ID": str(uuid.uuid4()),
    }
    team = os.environ.get("ROBOFLEET_AGENT_TEAM", "")
    if team:
        h["X-Agent-Team"] = team
    token = os.environ.get("ROBOFLEET_AGENT_TOKEN", "")
    if token and token != "UNSIGNED":
        h["X-Agent-Token"] = token
    return h


def _envelope_or_error(resp: httpx.Response) -> dict[str, Any]:
    """Return the JSON envelope, or a synthesized transport-error envelope."""
    try:
        data: dict[str, Any] = resp.json()
    except Exception:
        return {
            "error": "transport",
            "message": resp.text[:500],
            "remediate": "Re-issue the verb.",
            "missing": [],
        }
    if "status" not in data and "error" not in data:
        return {
            "error": "transport",
            "message": resp.text[:500],
            "remediate": "Re-issue the verb.",
            "missing": [],
        }
    return data


async def call_verb(verb: str, body: dict[str, Any]) -> dict[str, Any]:
    """POST a flow verb to the orchestrator gateway, return the Envelope dict."""
    public = _INTENT_TO_PUBLIC.get(verb, verb)
    url = f"{_base()}/api/v1/flow/{_segment()}/{public}"
    async with httpx.AsyncClient(timeout=httpx.Timeout(900.0)) as client:
        resp = await client.post(url, json=body, headers=_headers())
    return _envelope_or_error(resp)


async def call_do(tool: str, body: dict[str, Any]) -> dict[str, Any]:
    """POST a do-tool call to the orchestrator gateway, return the Envelope dict."""
    url = f"{_base()}/api/v1/do/{tool}"
    async with httpx.AsyncClient(timeout=httpx.Timeout(190.0)) as client:
        resp = await client.post(url, json=body, headers=_headers())
    return _envelope_or_error(resp)


def _load_manifest() -> dict[str, Any]:
    """Load the tool manifest from ROBOFLEET_TOOL_MANIFEST_PATH.

    Supports ``gs://`` URIs (fetched lazily from GCS) and local paths. Falls
    back to ``{}`` when the default local path is absent (local-dev with no
    manifest mounted): callers degrade to no tools / empty system_prompt
    rather than crashing on a missing file. A genuine parse error on a present
    file still raises. Shared by gateway_shim (tool registration) and
    adk_entry (system_prompt) so the gs://-or-local fetch logic is not
    duplicated.
    """
    path = os.environ.get("ROBOFLEET_TOOL_MANIFEST_PATH", _DEFAULT_MANIFEST)
    if path.startswith("gs://"):
        return _load_manifest_from_gcs(path)
    local = Path(path)
    if not local.exists():
        return {}
    return cast("dict[str, Any]", json.loads(local.read_text()))


def _load_manifest_from_gcs(gs_uri: str) -> dict[str, Any]:
    """Fetch and parse the manifest JSON blob from a ``gs://`` URI."""
    import google.cloud.storage  # lazy: only needed on the Cloud Run path

    bucket_name, _, blob_path = gs_uri[len("gs://") :].partition("/")
    client = google.cloud.storage.Client()
    blob = client.bucket(bucket_name).blob(blob_path)
    return cast("dict[str, Any]", json.loads(blob.download_as_text()))


# The orchestrator manifest carries only verb names (no JSON-schema), so a
# generic ``async def _fn(**kwargs)`` would make ADK declare every verb with an
# empty parameter set and the model could never pass task_id to i_will_work_on.
# ADK's JSON-schema declaration path rebuilds the schema from the function's
# real code params (not an overridden __signature__), so verbs that take args
# need a real named signature. These specialized functions carry real typed
# params; every other verb stays no-arg via the generic maker below, which is
# correct for give_me_work / i_am_idle / open_pr / sync_branch / etc.
async def _i_will_work_on(
    task_id: str,
    plan: str,
    steps: list[dict[str, str]],
    technical_considerations: list[str],
    risks: list[dict[str, str]],
) -> dict[str, Any]:
    """Claim a task (pending -> claimed -> in_progress) and start work. Pass the
    task_id from give_me_work's response, plus the same rich plan a PM authors
    so the task's Plan tab is filled: ``plan`` is the approach (>=150 chars
    describing HOW you will implement), ``steps`` is a non-empty execution
    checklist of {"title","description"} with each description >=60 chars,
    ``technical_considerations`` is a list of strings, and ``risks`` is a list
    of {"risk","mitigation"}. The orchestrator rejects a thin plan.
    """
    return await call_verb(
        "i_will_work_on",
        {
            "task_id": task_id,
            "plan": plan,
            "steps": steps,
            "technical_considerations": technical_considerations,
            "risks": risks,
        },
    )


async def _resume(task_id: str) -> dict[str, Any]:
    """Resume a paused task. Pass the task_id."""
    return await call_verb("resume", {"task_id": task_id})


async def _unclaim(task_id: str = "") -> dict[str, Any]:
    """Release a claimed task back to the pool. Pass the task_id (or omit for the current task)."""
    return await call_verb("unclaim", {"task_id": task_id} if task_id else {})


async def _i_am_blocked(reason: str) -> dict[str, Any]:
    """Signal you are blocked. Pass a short reason."""
    return await call_verb("i_am_blocked", {"reason": reason})


async def _note(scope: str, content: str) -> dict[str, Any]:
    """Write a journal/note entry. scope is e.g. 'handoff' or 'reflect'; content is the text."""
    return await call_do("note", {"scope": scope, "content": content})


async def _commit(message: str, files: list[str] | None = None) -> dict[str, Any]:
    """Commit staged files. Pass the commit message; optionally the file paths."""
    body: dict[str, Any] = {"message": message}
    if files:
        body["files"] = files
    return await call_do("commit", body)


async def _progress(content: str) -> dict[str, Any]:
    """Record a progress update. Pass the update text."""
    return await call_do("progress", {"content": content})


# Verb/tool name -> specialized function with a real signature.
_SPECIALIZED: dict[str, Any] = {
    "i_will_work_on": _i_will_work_on,
    "resume": _resume,
    "unclaim": _unclaim,
    "i_am_blocked": _i_am_blocked,
    "note": _note,
    "commit": _commit,
    "progress": _progress,
}


def _make_flow_tool(verb: str) -> FunctionTool:
    public = _INTENT_TO_PUBLIC.get(verb, verb)
    specialized = _SPECIALIZED.get(verb) or _SPECIALIZED.get(public)
    if specialized is not None:
        specialized.__name__ = public
        return FunctionTool(specialized)
    async def _fn(**kwargs: Any) -> dict[str, Any]:
        return await call_verb(verb, kwargs)

    _fn.__name__ = public
    return FunctionTool(_fn)


def _make_do_tool(tool: str) -> FunctionTool:
    specialized = _SPECIALIZED.get(tool)
    if specialized is not None:
        specialized.__name__ = tool
        return FunctionTool(specialized)
    async def _fn(**kwargs: Any) -> dict[str, Any]:
        return await call_do(tool, kwargs)

    _fn.__name__ = tool
    return FunctionTool(_fn)


def build_gateway_tools() -> list[FunctionTool]:
    """Build one ADK FunctionTool per manifest flow/do entry."""
    manifest = _load_manifest()
    tools: list[FunctionTool] = []
    for verb in manifest.get("flow_tools", []):
        tools.append(_make_flow_tool(verb))
    for tool in manifest.get("do_tools", []):
        tools.append(_make_do_tool(tool))
    return tools
