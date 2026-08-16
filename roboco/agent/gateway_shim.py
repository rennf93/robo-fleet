"""ADK tool shim: maps role flow/do verbs to orchestrator HTTP routes.

The agent process talks to the existing orchestrator gateway over HTTP instead
of MCP servers. Flow verbs POST to ``{base}/api/v1/flow/{segment}/{verb}`` where
``segment`` is ``"board"`` for product_owner/head_marketing, else the role
string. Do tools POST to ``{base}/api/v1/do/{tool}``. The intent->public verb
remap (``pass_review``->``pass``, ``fail_review``->``fail``) mirrors the route
registration in ``roboco/api/routes/v1/flow_qa.py``; the PR-gate verbs
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

# product_owner/head_marketing share the /flow/board segment (flow_board.py).
_BOARD_ROLES = {"product_owner", "head_marketing"}
# Intent verbs (manifest) -> public route names. Confirmed against flow_qa.py:
# /pass and /fail are the registered routes; pass_review/fail_review are the
# intent-verb names emitted by lifecycle.intents_for_role(Role.QA).
_INTENT_TO_PUBLIC: dict[str, str] = {"pass_review": "pass", "fail_review": "fail"}

_DEFAULT_BASE = "http://roboco-orchestrator:8000"
_DEFAULT_MANIFEST = "/app/tool-manifest.json"


def _base() -> str:
    return os.environ.get("ROBOCO_ORCHESTRATOR_URL", _DEFAULT_BASE)


def _segment() -> str:
    role = os.environ.get("ROBOCO_AGENT_ROLE", "")
    return "board" if role in _BOARD_ROLES else role


def _headers() -> dict[str, str]:
    h: dict[str, str] = {
        "X-Agent-ID": os.environ.get("ROBOCO_AGENT_ID", ""),
        "X-Agent-Role": os.environ.get("ROBOCO_AGENT_ROLE", ""),
        "X-Correlation-ID": str(uuid.uuid4()),
    }
    team = os.environ.get("ROBOCO_AGENT_TEAM", "")
    if team:
        h["X-Agent-Team"] = team
    token = os.environ.get("ROBOCO_AGENT_TOKEN", "")
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
    """Load the tool manifest from ROBOCO_TOOL_MANIFEST_PATH.

    Supports ``gs://`` URIs (fetched lazily from GCS) and local paths. Falls
    back to ``{}`` when the default local path is absent (local-dev with no
    manifest mounted): callers degrade to no tools / empty system_prompt
    rather than crashing on a missing file. A genuine parse error on a present
    file still raises. Shared by gateway_shim (tool registration) and
    adk_entry (system_prompt) so the gs://-or-local fetch logic is not
    duplicated.
    """
    path = os.environ.get("ROBOCO_TOOL_MANIFEST_PATH", _DEFAULT_MANIFEST)
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


def _make_flow_tool(verb: str) -> FunctionTool:
    public = _INTENT_TO_PUBLIC.get(verb, verb)

    async def _fn(**kwargs: Any) -> dict[str, Any]:
        return await call_verb(verb, kwargs)

    _fn.__name__ = public
    return FunctionTool(_fn)


def _make_do_tool(tool: str) -> FunctionTool:
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
