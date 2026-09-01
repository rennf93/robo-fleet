"""Guard: no pre-gateway tool names may appear in live ``robofleet/`` sources.

The Gateway/full cutover deleted the v1 per-domain MCP tools. Any surviving
reference in a spawn prompt, seed, onboarding string, or comment hands agents
(or future readers) a tool that no longer exists. This test fails if any
reappear.

The orphaned ``robofleet/agents/`` subtree is excluded — it is pre-gateway dead
code removed wholesale in a later phase, so there is no value in scrubbing its
strings first.
"""

from __future__ import annotations

import pathlib
import re

# Deleted v1 tool names (the gateway replaced them with bare verbs like
# give_me_work / i_am_done / triage / notify / note). robofleet_ask_mentor and
# robofleet_kb_search are intentionally absent — those are still live.
FORBIDDEN: tuple[str, ...] = (
    "robofleet_task_scan",
    "robofleet_task_claim",
    "robofleet_task_get",
    "robofleet_task_complete",
    "robofleet_task_escalate",
    "robofleet_task_escalate_to_ceo",
    "robofleet_task_substitute",
    "robofleet_task_submit_qa",
    "robofleet_task_submit_verification",
    "robofleet_task_submit_pm_review",
    "robofleet_task_qa_pass",
    "robofleet_task_qa_fail",
    "robofleet_task_docs_complete",
    "robofleet_task_create",
    "robofleet_task_activate",
    "robofleet_task_cancel",
    "robofleet_task_plan",
    "robofleet_task_start",
    "robofleet_task_progress",
    "robofleet_task_pause",
    "robofleet_task_block",
    "robofleet_task_unblock",
    "robofleet_agent_idle",
    "robofleet_escalate",
    "robofleet_notify_ack",
    "robofleet_notify_send",
    "robofleet_notify_list",
    "robofleet_notify_get",
    "robofleet_message_send",
    "robofleet_session_create_for_tasks",
    "robofleet_journal_decision",
    "robofleet_journal_learning",
    "robofleet_journal_struggle",
    "robofleet_journal_reflect",
    "robofleet_journal_entry",
)

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_PKG = _ROOT / "robofleet"
# Pre-gateway agent subtree, removed wholesale in a later phase.
_EXCLUDED_DIR = _PKG / "agents"


def _excluded(path: pathlib.Path) -> bool:
    return _EXCLUDED_DIR in path.parents


def test_no_deleted_tool_names_in_runtime_sources() -> None:
    hits: list[str] = []
    for path in _PKG.rglob("*.py"):
        if _excluded(path):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name in FORBIDDEN:
            if name in text:
                hits.append(f"{path.relative_to(_ROOT)} :: {name}")
    assert not hits, "Deleted v1 tool names still referenced:\n" + "\n".join(hits)


# ---------------------------------------------------------------------------
# Hook scripts run at agent runtime and are invisible to the Python import
# graph + mypy. A deleted tool name or a deleted SDK endpoint referenced in a
# hook script breaks silently in the agent container (the traceability-hook
# regression: it kept curling a /traceability/remind endpoint deleted from the
# SDK, 404ing on every gateway tool call). These guards scan docker/scripts/*.sh.
# ---------------------------------------------------------------------------

_HOOK_DIR = _ROOT / "docker" / "scripts"
_SDK_SERVER = _PKG / "agent_sdk" / "server.py"


def test_no_deleted_tool_names_in_hook_scripts() -> None:
    hits: list[str] = []
    for path in _HOOK_DIR.glob("*.sh"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name in FORBIDDEN:
            if name in text:
                hits.append(f"{path.relative_to(_ROOT)} :: {name}")
    assert not hits, (
        "Deleted v1 tool names still referenced in hook scripts:\n" + "\n".join(hits)
    )


def test_hook_scripts_curl_only_existing_sdk_endpoints() -> None:
    """Every `$SDK_URL/<path>` a hook curls must be a route still served by the SDK."""
    server = _SDK_SERVER.read_text(encoding="utf-8", errors="ignore")
    defined = set(
        re.findall(
            r"""@app\.(?:get|post|put|patch|delete)\(\s*["']([^"'?]+)["']""",
            server,
        )
    )
    assert defined, "could not parse any routes from agent_sdk/server.py"

    dangling: list[str] = []
    for path in _HOOK_DIR.glob("*.sh"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        # Static path right after $SDK_URL/ — stop at ?, ", whitespace, or $VAR.
        for route in re.findall(r"\$SDK_URL/([A-Za-z0-9_/-]+)", text):
            if "/" + route not in defined:
                dangling.append(f"{path.relative_to(_ROOT)} :: $SDK_URL/{route}")
    assert not dangling, (
        "Hook scripts curl SDK endpoints that no longer exist in agent_sdk/server.py "
        "(remove the hook or restore the endpoint):\n" + "\n".join(dangling)
    )
