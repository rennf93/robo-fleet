"""Tests for the ADK gateway tool-shim (robofleet.agent.gateway_shim)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest


@pytest.mark.asyncio
async def test_flow_tool_posts_to_role_segment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        '{"flow_tools": ["give_me_work", "i_am_done"], "do_tools": ["commit"]}'
    )
    monkeypatch.setenv("ROBOFLEET_ORCHESTRATOR_URL", "http://orch:8000")
    monkeypatch.setenv("ROBOFLEET_AGENT_ID", "11111111-1111-1111-1111-111111111111")
    monkeypatch.setenv("ROBOFLEET_AGENT_ROLE", "developer")
    monkeypatch.setenv("ROBOFLEET_AGENT_TOKEN", "tok")
    monkeypatch.setenv("ROBOFLEET_TOOL_MANIFEST_PATH", str(manifest))
    captured: dict[str, Any] = {}

    async def fake_post(self: httpx.AsyncClient, url: str, **kw: Any) -> httpx.Response:
        captured["url"] = url
        captured["headers"] = kw.get("headers", {})
        return httpx.Response(200, json={"status": "ok", "next": "i_will_work_on"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    from robofleet.agent.gateway_shim import call_verb

    env = await call_verb("give_me_work", {})
    assert captured["url"] == "http://orch:8000/api/v1/flow/developer/give_me_work"
    assert captured["headers"]["X-Agent-ID"] == "11111111-1111-1111-1111-111111111111"
    assert captured["headers"]["X-Agent-Role"] == "developer"
    assert captured["headers"]["X-Agent-Token"] == "tok"
    assert "X-Agent-Team" not in captured["headers"]
    assert env["status"] == "ok"


@pytest.mark.asyncio
async def test_board_role_uses_board_segment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"flow_tools": ["triage"], "do_tools": []}')
    monkeypatch.setenv("ROBOFLEET_ORCHESTRATOR_URL", "http://orch:8000")
    monkeypatch.setenv("ROBOFLEET_AGENT_ID", "22222222-2222-2222-2222-222222222222")
    monkeypatch.setenv("ROBOFLEET_AGENT_ROLE", "product_owner")
    monkeypatch.setenv("ROBOFLEET_TOOL_MANIFEST_PATH", str(manifest))
    captured: dict[str, Any] = {}

    async def fake_post(self: httpx.AsyncClient, url: str, **kw: Any) -> httpx.Response:
        captured["url"] = url
        return httpx.Response(200, json={"status": "ok"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    from robofleet.agent.gateway_shim import call_verb

    await call_verb("triage", {})
    assert captured["url"] == "http://orch:8000/api/v1/flow/board/triage"


@pytest.mark.asyncio
async def test_intent_to_public_remap_pass_review(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """QA pass_review/fail_review map to public /pass and /fail routes."""
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        '{"flow_tools": ["pass_review", "fail_review"], "do_tools": []}'
    )
    monkeypatch.setenv("ROBOFLEET_ORCHESTRATOR_URL", "http://orch:8000")
    monkeypatch.setenv("ROBOFLEET_AGENT_ID", "33333333-3333-3333-3333-333333333333")
    monkeypatch.setenv("ROBOFLEET_AGENT_ROLE", "qa")
    monkeypatch.setenv("ROBOFLEET_TOOL_MANIFEST_PATH", str(manifest))
    captured: list[str] = []

    async def fake_post(self: httpx.AsyncClient, url: str, **kw: Any) -> httpx.Response:
        captured.append(url)
        return httpx.Response(200, json={"status": "ok"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    from robofleet.agent.gateway_shim import call_verb

    await call_verb("pass_review", {"task_id": "t1"})
    await call_verb("fail_review", {"task_id": "t1"})
    assert captured == [
        "http://orch:8000/api/v1/flow/qa/pass",
        "http://orch:8000/api/v1/flow/qa/fail",
    ]


@pytest.mark.asyncio
async def test_unsigned_token_omitted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"flow_tools": ["give_me_work"], "do_tools": []}')
    monkeypatch.setenv("ROBOFLEET_ORCHESTRATOR_URL", "http://orch:8000")
    monkeypatch.setenv("ROBOFLEET_AGENT_ID", "44444444-4444-4444-4444-444444444444")
    monkeypatch.setenv("ROBOFLEET_AGENT_ROLE", "developer")
    monkeypatch.setenv("ROBOFLEET_AGENT_TOKEN", "UNSIGNED")
    monkeypatch.delenv("ROBOFLEET_AGENT_TEAM", raising=False)
    monkeypatch.setenv("ROBOFLEET_TOOL_MANIFEST_PATH", str(manifest))
    captured: dict[str, Any] = {}

    async def fake_post(self: httpx.AsyncClient, url: str, **kw: Any) -> httpx.Response:
        captured["headers"] = kw.get("headers", {})
        return httpx.Response(200, json={"status": "ok"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    from robofleet.agent.gateway_shim import call_verb

    await call_verb("give_me_work", {})
    assert "X-Agent-Token" not in captured["headers"]


@pytest.mark.asyncio
async def test_call_do_posts_to_do_route(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ROBOFLEET_ORCHESTRATOR_URL", "http://orch:8000")
    monkeypatch.setenv("ROBOFLEET_AGENT_ID", "55555555-5555-5555-5555-555555555555")
    monkeypatch.setenv("ROBOFLEET_AGENT_ROLE", "developer")
    monkeypatch.delenv("ROBOFLEET_AGENT_TOKEN", raising=False)
    captured: dict[str, Any] = {}

    async def fake_post(self: httpx.AsyncClient, url: str, **kw: Any) -> httpx.Response:
        captured["url"] = url
        captured["headers"] = kw.get("headers", {})
        return httpx.Response(200, json={"status": "ok"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    from robofleet.agent.gateway_shim import call_do

    await call_do("commit", {"message": "m"})
    assert captured["url"] == "http://orch:8000/api/v1/do/commit"
    assert "X-Agent-Token" not in captured["headers"]


@pytest.mark.asyncio
async def test_specialized_shims_send_server_schema_field_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The specialized shim functions must send the field names the server
    Pydantic schemas require, not names derived from the function params.

    ADK declares a tool's params FROM the function signature, so the param
    name and the wire field name are the same. A mismatch (e.g. _note param
    ``content`` while NoteRequest requires ``text``) is a double-bind: the
    server 422s on the wrong field, and ADK rejects omitting it. This pins
    the three specialized tools whose server schemas require specific names.
    """
    monkeypatch.setenv("ROBOFLEET_ORCHESTRATOR_URL", "http://orch:8000")
    monkeypatch.setenv("ROBOFLEET_AGENT_ID", "77777777-7777-7777-7777-777777777777")
    monkeypatch.setenv("ROBOFLEET_AGENT_ROLE", "developer")
    monkeypatch.setenv("ROBOFLEET_AGENT_TOKEN", "tok")
    posts: list[dict[str, Any]] = []

    async def fake_post(self: httpx.AsyncClient, url: str, **kw: Any) -> httpx.Response:
        posts.append({"url": url, "json": kw.get("json", {})})
        return httpx.Response(200, json={"status": "ok"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    from robofleet.agent.gateway_shim import (
        _claim_review,
        _i_am_blocked,
        _i_am_done,
        _note,
        _open_pr,
        _pass_review,
        _progress,
    )

    await _note("note", "claiming task 660d59ce")
    await _i_am_blocked("660d59ce", "rate limited", blocker_type="external")
    await _progress("660d59ce", "wrote README", plan_step="1")
    await _open_pr("660d59ce")
    await _i_am_done("660d59ce", notes="done")
    await _claim_review("660d59ce")
    await _pass_review(
        "660d59ce",
        "looks good",
        criteria_verified=[{"criterion": "ac1", "evidence": "f:1"}],
    )

    note_body = next(p["json"] for p in posts if p["url"].endswith("/do/note"))
    assert note_body["text"] == "claiming task 660d59ce"
    assert "content" not in note_body

    blocked_body = next(
        p["json"] for p in posts if p["url"].endswith("/flow/developer/i_am_blocked")
    )
    assert blocked_body["task_id"] == "660d59ce"
    assert blocked_body["reason"] == "rate limited"
    assert blocked_body["blocker_type"] == "external"

    progress_body = next(p["json"] for p in posts if p["url"].endswith("/do/progress"))
    assert progress_body["task_id"] == "660d59ce"
    assert progress_body["message"] == "wrote README"
    assert "content" not in progress_body

    open_pr_body = next(
        p["json"] for p in posts if p["url"].endswith("/flow/developer/open_pr")
    )
    assert open_pr_body == {"task_id": "660d59ce"}

    done_body = next(
        p["json"] for p in posts if p["url"].endswith("/flow/developer/i_am_done")
    )
    assert done_body["task_id"] == "660d59ce"
    assert done_body["notes"] == "done"

    # Role is "developer" so QA verbs route to /flow/developer/* here; the
    # segment is the agent's own role, not the verb's canonical role.
    claim_body = next(
        p["json"] for p in posts if p["url"].endswith("/flow/developer/claim_review")
    )
    assert claim_body == {"task_id": "660d59ce"}

    pass_body = next(
        p["json"] for p in posts if p["url"].endswith("/flow/developer/pass")
    )
    assert pass_body["task_id"] == "660d59ce"
    assert pass_body["criteria_verified"][0]["criterion"] == "ac1"


@pytest.mark.asyncio
async def test_every_manifest_arg_verb_is_specialized(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No arg-taking flow/do verb may fall through to the generic ``**kwargs``
    maker: ADK declares an empty param set for it and strips every arg the
    model passes (the live open_pr/task_id-stripped incident). Every verb whose
    server schema requires a field must have a real signature in _SPECIALIZED.
    """
    from robofleet.agent.gateway_shim import _SPECIALIZED

    # Arg-taking verbs that the minimal E2E cycle + common delivery tools hit.
    must_be_specialized = {
        "i_will_work_on",
        "open_pr",
        "i_am_done",
        "i_am_blocked",
        "unclaim",
        "resume",
        "sync_branch",
        "claim_review",
        "pass_review",
        "fail_review",
        "claim_pr_review",
        "post_pr_review",
        "claim_gate_review",
        "pr_pass",
        "pr_fail",
        "claim_doc_task",
        "i_documented",
        "complete",
        "request_changes",
        "submit_up",
        "submit_root",
        "unblock",
        "escalate_up",
        "escalate_to_ceo",
        "reassign",
        "declare_coverage",
        "i_will_plan",
        "delegate",
        "waive_finding",
        "note",
        "commit",
        "progress",
        "evidence",
        "dm",
        "draft_playbook",
    }
    missing = must_be_specialized - set(_SPECIALIZED)
    assert not missing, (
        f"unspecialized arg-taking verbs (ADK would strip args): {missing}"
    )


def test_build_gateway_tools_wraps_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """build_gateway_tools returns one FunctionTool per manifest entry."""
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"flow_tools": ["give_me_work"], "do_tools": ["commit"]}')
    monkeypatch.setenv("ROBOFLEET_ORCHESTRATOR_URL", "http://orch:8000")
    monkeypatch.setenv("ROBOFLEET_AGENT_ID", "66666666-6666-6666-6666-666666666666")
    monkeypatch.setenv("ROBOFLEET_AGENT_ROLE", "developer")
    monkeypatch.setenv("ROBOFLEET_TOOL_MANIFEST_PATH", str(manifest))
    from robofleet.agent.gateway_shim import build_gateway_tools

    tools = build_gateway_tools()
    assert len(tools) == 2
    names = {getattr(t, "name", None) for t in tools}
    # FunctionTool exposes the wrapped function name
    assert any("give_me_work" in str(n) for n in names if n)


@pytest.mark.asyncio
async def test_note_forwards_handoff_and_structured_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """scope='handoff' must reach the server with done/next: the tracing gate
    behind delegate/i_am_done requires them, and a shim that only forwarded
    scope/text/task_id made every ADK handoff note fail (110 rejected notes in
    one Main PM run). Empty optional fields stay off the wire."""
    monkeypatch.setenv("ROBOFLEET_ORCHESTRATOR_URL", "http://orch:8000")
    monkeypatch.setenv("ROBOFLEET_AGENT_ID", "77777777-7777-7777-7777-777777777777")
    monkeypatch.setenv("ROBOFLEET_AGENT_ROLE", "main_pm")
    monkeypatch.setenv("ROBOFLEET_AGENT_TOKEN", "tok")
    posts: list[dict[str, Any]] = []

    async def fake_post(self: httpx.AsyncClient, url: str, **kw: Any) -> httpx.Response:
        posts.append({"url": url, "json": kw.get("json", {})})
        return httpx.Response(200, json={"status": "noted"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    from robofleet.agent.gateway_shim import _note

    await _note(
        "handoff",
        "handoff before delegate",
        "660d59ce",
        done="planned the backend split",
        next="be-pm delegates two dev leaves",
        where_to_look=["robofleet/tree_check.py"],
    )
    await _note("note", "plain note")
    handoff, plain = (p["json"] for p in posts)
    assert handoff["scope"] == "handoff"
    assert handoff["done"] == "planned the backend split"
    assert handoff["next"] == "be-pm delegates two dev leaves"
    assert handoff["where_to_look"] == ["robofleet/tree_check.py"]
    assert handoff["task_id"] == "660d59ce"
    assert set(plain) == {"scope", "text"}
