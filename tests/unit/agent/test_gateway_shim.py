"""Tests for the ADK gateway tool-shim (roboco.agent.gateway_shim)."""

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
    monkeypatch.setenv("ROBOCO_ORCHESTRATOR_URL", "http://orch:8000")
    monkeypatch.setenv("ROBOCO_AGENT_ID", "11111111-1111-1111-1111-111111111111")
    monkeypatch.setenv("ROBOCO_AGENT_ROLE", "developer")
    monkeypatch.setenv("ROBOCO_AGENT_TOKEN", "tok")
    monkeypatch.setenv("ROBOCO_TOOL_MANIFEST_PATH", str(manifest))
    captured: dict[str, Any] = {}

    async def fake_post(self: httpx.AsyncClient, url: str, **kw: Any) -> httpx.Response:
        captured["url"] = url
        captured["headers"] = kw.get("headers", {})
        return httpx.Response(200, json={"status": "ok", "next": "i_will_work_on"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    from roboco.agent.gateway_shim import call_verb

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
    monkeypatch.setenv("ROBOCO_ORCHESTRATOR_URL", "http://orch:8000")
    monkeypatch.setenv("ROBOCO_AGENT_ID", "22222222-2222-2222-2222-222222222222")
    monkeypatch.setenv("ROBOCO_AGENT_ROLE", "product_owner")
    monkeypatch.setenv("ROBOCO_TOOL_MANIFEST_PATH", str(manifest))
    captured: dict[str, Any] = {}

    async def fake_post(self: httpx.AsyncClient, url: str, **kw: Any) -> httpx.Response:
        captured["url"] = url
        return httpx.Response(200, json={"status": "ok"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    from roboco.agent.gateway_shim import call_verb

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
    monkeypatch.setenv("ROBOCO_ORCHESTRATOR_URL", "http://orch:8000")
    monkeypatch.setenv("ROBOCO_AGENT_ID", "33333333-3333-3333-3333-333333333333")
    monkeypatch.setenv("ROBOCO_AGENT_ROLE", "qa")
    monkeypatch.setenv("ROBOCO_TOOL_MANIFEST_PATH", str(manifest))
    captured: list[str] = []

    async def fake_post(self: httpx.AsyncClient, url: str, **kw: Any) -> httpx.Response:
        captured.append(url)
        return httpx.Response(200, json={"status": "ok"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    from roboco.agent.gateway_shim import call_verb

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
    monkeypatch.setenv("ROBOCO_ORCHESTRATOR_URL", "http://orch:8000")
    monkeypatch.setenv("ROBOCO_AGENT_ID", "44444444-4444-4444-4444-444444444444")
    monkeypatch.setenv("ROBOCO_AGENT_ROLE", "developer")
    monkeypatch.setenv("ROBOCO_AGENT_TOKEN", "UNSIGNED")
    monkeypatch.delenv("ROBOCO_AGENT_TEAM", raising=False)
    monkeypatch.setenv("ROBOCO_TOOL_MANIFEST_PATH", str(manifest))
    captured: dict[str, Any] = {}

    async def fake_post(self: httpx.AsyncClient, url: str, **kw: Any) -> httpx.Response:
        captured["headers"] = kw.get("headers", {})
        return httpx.Response(200, json={"status": "ok"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    from roboco.agent.gateway_shim import call_verb

    await call_verb("give_me_work", {})
    assert "X-Agent-Token" not in captured["headers"]


@pytest.mark.asyncio
async def test_call_do_posts_to_do_route(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ROBOCO_ORCHESTRATOR_URL", "http://orch:8000")
    monkeypatch.setenv("ROBOCO_AGENT_ID", "55555555-5555-5555-5555-555555555555")
    monkeypatch.setenv("ROBOCO_AGENT_ROLE", "developer")
    monkeypatch.delenv("ROBOCO_AGENT_TOKEN", raising=False)
    captured: dict[str, Any] = {}

    async def fake_post(self: httpx.AsyncClient, url: str, **kw: Any) -> httpx.Response:
        captured["url"] = url
        captured["headers"] = kw.get("headers", {})
        return httpx.Response(200, json={"status": "ok"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    from roboco.agent.gateway_shim import call_do

    await call_do("commit", {"message": "m"})
    assert captured["url"] == "http://orch:8000/api/v1/do/commit"
    assert "X-Agent-Token" not in captured["headers"]


def test_build_gateway_tools_wraps_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """build_gateway_tools returns one FunctionTool per manifest entry."""
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"flow_tools": ["give_me_work"], "do_tools": ["commit"]}')
    monkeypatch.setenv("ROBOCO_ORCHESTRATOR_URL", "http://orch:8000")
    monkeypatch.setenv("ROBOCO_AGENT_ID", "66666666-6666-6666-6666-666666666666")
    monkeypatch.setenv("ROBOCO_AGENT_ROLE", "developer")
    monkeypatch.setenv("ROBOCO_TOOL_MANIFEST_PATH", str(manifest))
    from roboco.agent.gateway_shim import build_gateway_tools

    tools = build_gateway_tools()
    assert len(tools) == 2
    names = {getattr(t, "name", None) for t in tools}
    # FunctionTool exposes the wrapped function name
    assert any("give_me_work" in str(n) for n in names if n)
