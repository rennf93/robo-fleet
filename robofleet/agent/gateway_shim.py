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
from urllib.parse import urlparse

import httpx
from google.adk.tools import FunctionTool

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
# generic ``async def _fn(**kwargs)`` declares an EMPTY parameter set and ADK
# strips every arg the model passes. ADK builds the tool schema from the
# function's real code params, so any verb that takes args needs a real named
# signature with the exact server-schema field names. Only truly no-arg verbs
# (give_me_work, i_am_idle, triage) stay on the generic maker below. Every
# specialized function's docstring IS the ADK tool description, so it names the
# required fields.
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
    """Release a claimed task back to the pool. Pass the task_id, or
    omit for the current task."""
    return await call_verb("unclaim", {"task_id": task_id} if task_id else {})


async def _i_am_blocked(
    task_id: str, reason: str, blocker_type: str = "", what_needed: str = ""
) -> dict[str, Any]:
    """Signal you are blocked. task_id is required. Pass a short reason;
    optionally blocker_type (one of external|internal|question|dependency)
    and what_needed (what would unblock you)."""
    body: dict[str, Any] = {"task_id": task_id, "reason": reason}
    if blocker_type:
        body["blocker_type"] = blocker_type
    if what_needed:
        body["what_needed"] = what_needed
    return await call_verb("i_am_blocked", body)


async def _note(scope: str, text: str, task_id: str = "") -> dict[str, Any]:
    """Write a journal/note entry. scope is e.g. 'note', 'handoff' or 'reflect';
    text is the entry content. Pass task_id when you have an active task so the
    note links to it; omit it for the pre-claim tracing note."""
    body: dict[str, Any] = {"scope": scope, "text": text}
    if task_id:
        body["task_id"] = task_id
    return await call_do("note", body)


async def _commit(message: str, files: list[str] | None = None) -> dict[str, Any]:
    """Commit staged files. Pass the commit message; optionally the file paths."""
    body: dict[str, Any] = {"message": message}
    if files:
        body["files"] = files
    return await call_do("commit", body)


async def _progress(
    task_id: str, message: str, plan_step: str = "", percentage: int | None = None
) -> dict[str, Any]:
    """Record a progress update. task_id is required. message is the update
    text. Optionally pass plan_step (a sub_task id or its 1-based order) to
    mark that step complete, or percentage (0-100) for tasks with no checklist."""
    body: dict[str, Any] = {"task_id": task_id, "message": message}
    if plan_step:
        body["plan_step"] = plan_step
    if percentage is not None:
        body["percentage"] = percentage
    return await call_do("progress", body)


async def _open_pr(task_id: str) -> dict[str, Any]:
    """Open the pull request for your current task. task_id is required
    (from give_me_work / i_will_work_on). Call after you have committed and
    pushed the branch."""
    return await call_verb("open_pr", {"task_id": task_id})


async def _sync_branch(task_id: str, stash: bool = False) -> dict[str, Any]:
    """Rebase your task branch onto its base branch (git-only, no DB state
    change). task_id is required. Pass stash=True to auto-stash uncommitted
    edits and pop them back after, instead of refusing on a dirty workspace."""
    body: dict[str, Any] = {"task_id": task_id}
    if stash:
        body["stash"] = True
    return await call_verb("sync_branch", body)


async def _i_am_done(
    task_id: str,
    notes: str = "",
    resolved_findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Submit your finished task for QA review (in_progress -> awaiting_qa).
    task_id is required. notes is an optional summary of what you did.
    resolved_findings is an optional list of {finding_id, commit?, note?}
    naming each open ledger finding you addressed (required when open
    findings exist). Call after open_pr."""
    body: dict[str, Any] = {"task_id": task_id, "notes": notes}
    if resolved_findings:
        body["resolved_findings"] = resolved_findings
    return await call_verb("i_am_done", body)


async def _claim_review(task_id: str) -> dict[str, Any]:
    """Claim a task for QA review (awaiting_qa -> claimed). task_id required."""
    return await call_verb("claim_review", {"task_id": task_id})


async def _pass_review(
    task_id: str,
    notes: str,
    criteria_verified: list[dict[str, Any]] | None = None,
    ac_verdicts: list[str] | None = None,
) -> dict[str, Any]:
    """Pass QA review (awaiting_qa -> awaiting_documentation). task_id and
    substantive notes are required. criteria_verified is mandatory when the
    task has acceptance criteria: one {criterion, evidence} entry per
    criterion, criterion matching an AC by id or exact text, evidence concrete
    (file:line, test name). Every criterion must be covered."""
    body: dict[str, Any] = {"task_id": task_id, "notes": notes}
    if criteria_verified is not None:
        body["criteria_verified"] = criteria_verified
    if ac_verdicts is not None:
        body["ac_verdicts"] = ac_verdicts
    return await call_verb("pass_review", body)


async def _fail_review(
    task_id: str,
    findings: list[dict[str, Any]] | None = None,
    issues: list[str] | None = None,
) -> dict[str, Any]:
    """Fail QA review back to the developer (awaiting_qa -> needs_revision).
    task_id required. Pass structured findings (list of {file?, line?, severity
    blocker|major|minor|nit, expected, actual, fix?, evidence?}) and/or legacy
    issues (list of strings). At least one of findings/issues is required."""
    body: dict[str, Any] = {"task_id": task_id}
    if findings:
        body["findings"] = findings
    if issues:
        body["issues"] = issues
    return await call_verb("fail_review", body)


async def _claim_pr_review(task_id: str) -> dict[str, Any]:
    """Claim an inbound external/fork PR for review. task_id required."""
    return await call_verb("claim_pr_review", {"task_id": task_id})


async def _post_pr_review(
    task_id: str,
    body: str,
    event: str = "REQUEST_CHANGES",
    findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Post a review on an inbound PR. task_id and a review body are required.
    event is APPROVE, REQUEST_CHANGES, or COMMENT (default REQUEST_CHANGES).
    REQUEST_CHANGES needs >=1 finding; APPROVE may not carry a blocker/major
    finding. findings is a list of {file, line?, severity, expected, actual}."""
    payload: dict[str, Any] = {"task_id": task_id, "body": body, "event": event}
    if findings:
        payload["findings"] = findings
    return await call_verb("post_pr_review", payload)


async def _claim_gate_review(task_id: str) -> dict[str, Any]:
    """Claim an in-path assembled-PR gate review. task_id required."""
    return await call_verb("claim_gate_review", {"task_id": task_id})


async def _pr_pass(task_id: str, notes: str) -> dict[str, Any]:
    """Pass the in-path PR gate (awaiting_pr_review -> awaiting_pm_review).
    task_id and notes required."""
    return await call_verb("pr_pass", {"task_id": task_id, "notes": notes})


async def _pr_fail(
    task_id: str,
    findings: list[dict[str, Any]] | None = None,
    issues: list[str] | None = None,
) -> dict[str, Any]:
    """Fail the in-path PR gate (awaiting_pr_review -> needs_revision).
    task_id required, plus findings and/or issues (at least one)."""
    body: dict[str, Any] = {"task_id": task_id}
    if findings:
        body["findings"] = findings
    if issues:
        body["issues"] = issues
    return await call_verb("pr_fail", body)


async def _claim_doc_task(task_id: str) -> dict[str, Any]:
    """Claim a documentation task. task_id required."""
    return await call_verb("claim_doc_task", {"task_id": task_id})


async def _i_documented(task_id: str, notes: str, files: list[str]) -> dict[str, Any]:
    """Mark documentation complete (awaiting_documentation -> awaiting_pm_review).
    task_id, notes, and the list of doc files written are all required."""
    return await call_verb(
        "i_documented", {"task_id": task_id, "notes": notes, "files": files}
    )


async def _complete(task_id: str, notes: str) -> dict[str, Any]:
    """PM: mark a reviewed task completed (awaiting_pm_review -> completed).
    task_id and notes required."""
    return await call_verb("complete", {"task_id": task_id, "notes": notes})


async def _request_changes(
    task_id: str,
    findings: list[dict[str, Any]] | None = None,
    issues: list[str] | None = None,
) -> dict[str, Any]:
    """PM: reject a task back to the dev (awaiting_pm_review -> needs_revision).
    task_id required, plus findings and/or issues (at least one)."""
    body: dict[str, Any] = {"task_id": task_id}
    if findings:
        body["findings"] = findings
    if issues:
        body["issues"] = issues
    return await call_verb("request_changes", body)


async def _submit_up(
    task_id: str,
    notes: str,
    resolved_findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """PM: open the cell->root assembled PR and submit for PR-gate review.
    task_id and notes required; resolved_findings optional (list of
    {finding_id, commit?, note?})."""
    body: dict[str, Any] = {"task_id": task_id, "notes": notes}
    if resolved_findings:
        body["resolved_findings"] = resolved_findings
    return await call_verb("submit_up", body)


async def _submit_root(
    task_id: str,
    notes: str,
    resolved_findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """PM: open the root->master assembled PR and submit for PR-gate review.
    task_id and notes required; resolved_findings optional."""
    body: dict[str, Any] = {"task_id": task_id, "notes": notes}
    if resolved_findings:
        body["resolved_findings"] = resolved_findings
    return await call_verb("submit_root", body)


async def _unblock(task_id: str, reason: str, restore: bool = True) -> dict[str, Any]:
    """PM: clear a block on a task (reason >=10 chars, recorded as a
    journal:decision). restore=True (default) re-queues it for the dev."""
    return await call_verb(
        "unblock", {"task_id": task_id, "reason": reason, "restore": restore}
    )


async def _escalate_up(task_id: str, reason: str) -> dict[str, Any]:
    """PM: escalate a task up to the next PM. task_id and reason required."""
    return await call_verb("escalate_up", {"task_id": task_id, "reason": reason})


async def _escalate_to_ceo(task_id: str, reason: str) -> dict[str, Any]:
    """PM: escalate a task to the CEO. task_id and reason required."""
    return await call_verb(
        "escalate_to_ceo", {"task_id": task_id, "reason": reason}
    )


async def _reassign(task_id: str, new_assignee: str) -> dict[str, Any]:
    """PM: reassign a task to another developer slug in your own cell.
    task_id and new_assignee required."""
    return await call_verb(
        "reassign", {"task_id": task_id, "new_assignee": new_assignee}
    )


async def _declare_coverage(task_id: str, criteria: list[str]) -> dict[str, Any]:
    """PM: stamp which parent acceptance criteria a child covers. task_id is
    the CHILD to stamp; criteria are the parent's ACs by id or exact text."""
    return await call_verb(
        "declare_coverage", {"task_id": task_id, "criteria": criteria}
    )


async def _i_will_plan(
    task_id: str,
    plan: str,
    approach: str,
    sub_tasks: list[dict[str, str]] | None = None,
    technical_considerations: list[str] | None = None,
    risks: list[dict[str, str]] | None = None,
    open_questions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """PM: claim a coordination root and start planning (claimed -> in_progress).
    task_id required. plan is a short summary (<=2000 chars). approach is the
    HOW (>=150 chars). sub_tasks is a list of {title, description}. Optional:
    technical_considerations (list[str]), risks (list of {risk, mitigation}),
    open_questions (list of {question, ...})."""
    body: dict[str, Any] = {
        "task_id": task_id,
        "plan": plan,
        "approach": approach,
    }
    if sub_tasks:
        body["sub_tasks"] = sub_tasks
    if technical_considerations:
        body["technical_considerations"] = technical_considerations
    if risks:
        body["risks"] = risks
    if open_questions:
        body["open_questions"] = open_questions
    return await call_verb("i_will_plan", body)


async def _delegate(
    parent_task_id: str,
    title: str,
    description: str,
    assigned_to: str,
    team: str,
    task_type: str,
    nature: str,
    estimated_complexity: str,
    acceptance_criteria: list[str],
    covers_parent_criteria: list[str] | None = None,
    intends_to_touch: list[str] | None = None,
    adds_migration: bool = False,
    touches_shared: bool = False,
    project_id: str | None = None,
) -> dict[str, Any]:
    """PM: create and assign a child subtask. parent_task_id, title, description
    (>=20 chars), assigned_to (dev slug), team, task_type, nature,
    estimated_complexity (low|medium|high|critical), and a non-empty
    acceptance_criteria list (<=7 items) are required. Optional:
    covers_parent_criteria (parent AC ids this subtask owns),
    intends_to_touch (file globs for collision sequencing), adds_migration,
    touches_shared, project_id."""
    body: dict[str, Any] = {
        "parent_task_id": parent_task_id,
        "title": title,
        "description": description,
        "assigned_to": assigned_to,
        "team": team,
        "task_type": task_type,
        "nature": nature,
        "estimated_complexity": estimated_complexity,
        "acceptance_criteria": acceptance_criteria,
        "adds_migration": adds_migration,
        "touches_shared": touches_shared,
    }
    if covers_parent_criteria:
        body["covers_parent_criteria"] = covers_parent_criteria
    if intends_to_touch:
        body["intends_to_touch"] = intends_to_touch
    if project_id:
        body["project_id"] = project_id
    return await call_verb("delegate", body)


async def _evidence(task_id: str) -> dict[str, Any]:
    """Fetch the assembled evidence brief for a task (AC coverage, prior
    findings, commits, handoff). task_id required."""
    return await call_do("evidence", {"task_id": task_id})


async def _dm(
    recipient: str, text: str, task_id: str = "", skill: str = ""
) -> dict[str, Any]:
    """Send a direct A2A message to a same-cell peer (agent slug). recipient
    and text are required. task_id links it to a task; skill tags the thread."""
    body: dict[str, Any] = {"recipient": recipient, "text": text}
    if task_id:
        body["task_id"] = task_id
    if skill:
        body["skill"] = skill
    return await call_do("dm", body)


async def _draft_playbook(
    title: str,
    problem: str,
    procedure: str,
    tags: list[str] | None = None,
    source_task_id: str = "",
) -> dict[str, Any]:
    """Draft a curated playbook (when-to-use + procedure) for the KB. title,
    problem, and procedure are required. Optional tags and source_task_id."""
    body: dict[str, Any] = {"title": title, "problem": problem, "procedure": procedure}
    if tags:
        body["tags"] = tags
    if source_task_id:
        body["source_task_id"] = source_task_id
    return await call_do("draft_playbook", body)


async def _waive_finding(finding_id: str, note: str) -> dict[str, Any]:
    """Auditor: waive a minor/nit finding (blocker/major must be fixed, never
    waived). finding_id and a note explaining why are required."""
    return await call_verb("waive_finding", {"finding_id": finding_id, "note": note})


# Verb/tool name -> specialized function with a real signature.
_SPECIALIZED: dict[str, Any] = {
    "i_will_work_on": _i_will_work_on,
    "resume": _resume,
    "unclaim": _unclaim,
    "i_am_blocked": _i_am_blocked,
    "open_pr": _open_pr,
    "sync_branch": _sync_branch,
    "i_am_done": _i_am_done,
    "claim_review": _claim_review,
    "pass_review": _pass_review,
    "fail_review": _fail_review,
    "claim_pr_review": _claim_pr_review,
    "post_pr_review": _post_pr_review,
    "claim_gate_review": _claim_gate_review,
    "pr_pass": _pr_pass,
    "pr_fail": _pr_fail,
    "claim_doc_task": _claim_doc_task,
    "i_documented": _i_documented,
    "complete": _complete,
    "request_changes": _request_changes,
    "submit_up": _submit_up,
    "submit_root": _submit_root,
    "unblock": _unblock,
    "escalate_up": _escalate_up,
    "escalate_to_ceo": _escalate_to_ceo,
    "reassign": _reassign,
    "declare_coverage": _declare_coverage,
    "i_will_plan": _i_will_plan,
    "delegate": _delegate,
    "waive_finding": _waive_finding,
    "note": _note,
    "commit": _commit,
    "progress": _progress,
    "evidence": _evidence,
    "dm": _dm,
    "draft_playbook": _draft_playbook,
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
