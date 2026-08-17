"""Claude Code capability lockdown.

The settings.json deny-rules below are generated for every spawned agent
container (the shared Claude Code harness state). The host's ~/.claude (OAuth
credential store) and ~/.claude.json are bind-mounted read-write into every
agent container; no role's job requires the LLM to read its own harness's
credentials, so the generated settings.json must deny the native Read tool
from the two files that carry them, and deny the `Task` subagent tool.

Leg D1 stripped the Claude CLI docker spawn path (the fall-through in
``_spawn_container``); the `--disable-slash-commands` / `--tools` argv tests
that rode on the deleted ``_append_image_and_claude_args`` are replaced by a
guard that a no-provider delivery spawn raises RuntimeError. The settings.json
deny-rule tests are unaffected (they exercise ``_generate_agent_settings``).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from robofleet.models.runtime import OrchestratorAgentConfig, SpawnGitContext
from robofleet.runtime.orchestrator import AgentOrchestrator

_WS = "/data/workspaces/robofleet-api/backend/be-dev-1"
_CELL = "/data/workspaces/robofleet-api/backend"


def _orch() -> AgentOrchestrator:
    with patch.object(AgentOrchestrator, "__init__", return_value=None):
        return AgentOrchestrator.__new__(AgentOrchestrator)


def _make_dev_config() -> OrchestratorAgentConfig:
    return OrchestratorAgentConfig(
        agent_id="be-dev-1",
        blueprint_path=Path("/app/agents/blueprints/be-dev-1.md"),
        model="sonnet",
        mcp_config_path=Path("/app/mcp-config.json"),
        git_context=SpawnGitContext(
            project_slug="robofleet-api",
            branch_name="feature/backend/TASK0001",
        ),
    )


class TestSharedClaudeCredentialsDenied:
    """Every role's generated settings.json blocks the Read tool from the
    shared ~/.claude OAuth credential store."""

    def test_developer_settings_deny_claude_credentials(self) -> None:
        orch = _orch()
        path = orch._generate_agent_settings(
            agent_id="be-dev-1",
            role="developer",
            workspace_path=_WS,
            cell_workspace_path=_CELL,
        )
        deny = json.loads(Path(path).read_text())["permissions"]["deny"]
        assert "Read(//home/agent/.claude/.credentials.json)" in deny, deny
        assert "Read(//home/agent/.claude.json)" in deny, deny

    def test_qa_settings_also_deny_claude_credentials(self) -> None:
        """Not just the writer roles — a read-only role gets the same base_deny."""
        orch = _orch()
        path = orch._generate_agent_settings(
            agent_id="be-qa",
            role="qa",
            workspace_path=_WS,
            cell_workspace_path=_CELL,
        )
        deny = json.loads(Path(path).read_text())["permissions"]["deny"]
        assert "Read(//home/agent/.claude/.credentials.json)" in deny, deny
        assert "Read(//home/agent/.claude.json)" in deny, deny

    def test_settings_set_include_co_authored_by_false(self) -> None:
        """Suppresses the CLI's default Claude co-author commit trailer —
        agent commits carry the agent's identity, not the model vendor's."""
        orch = _orch()
        path = orch._generate_agent_settings(
            agent_id="be-dev-1",
            role="developer",
            workspace_path=_WS,
            cell_workspace_path=_CELL,
        )
        assert json.loads(Path(path).read_text())["includeCoAuthoredBy"] is False

    def test_deny_uses_absolute_double_slash_form(self) -> None:
        """Per the #167 gotcha: a single leading / resolves against the
        settings.json project root, not the container filesystem root — an
        absolute container path deny needs the // form or it silently never
        matches."""
        orch = _orch()
        path = orch._generate_agent_settings(
            agent_id="be-dev-1",
            role="developer",
            workspace_path=_WS,
            cell_workspace_path=_CELL,
        )
        deny = json.loads(Path(path).read_text())["permissions"]["deny"]
        claude_denies = [d for d in deny if d.startswith("Read(") and ".claude" in d]
        assert claude_denies, deny
        for entry in claude_denies:
            inner = entry[entry.index("(") + 1 :]
            assert inner.startswith("//"), f"must use // absolute form: {entry}"


class TestSubagentBanned:
    """Every role's settings.json denies the `Task` subagent tool.

    `Task` is a default-permitted Claude Code built-in; under
    defaultMode=bypassPermissions the manifest/allowlist omission does NOT
    remove it — only an explicit `permissions.deny` entry does. Without this
    the fleet-wide subagent ban (CEO, 2026-07-09) is unenforced on the Claude
    path (the grok path already blocks it via `--disallowed-tools Agent`).
    """

    def test_developer_settings_deny_task(self) -> None:
        orch = _orch()
        path = orch._generate_agent_settings(
            agent_id="be-dev-1",
            role="developer",
            workspace_path=_WS,
            cell_workspace_path=_CELL,
        )
        deny = json.loads(Path(path).read_text())["permissions"]["deny"]
        assert "Task" in deny, deny

    def test_read_only_role_also_denies_task(self) -> None:
        """A read-only role (pr_reviewer, the top prompt-injection target)
        gets the same base_deny → no subagent escape hatch."""
        orch = _orch()
        path = orch._generate_agent_settings(
            agent_id="be-pr-reviewer",
            role="pr_reviewer",
            workspace_path=_WS,
            cell_workspace_path=_CELL,
        )
        deny = json.loads(Path(path).read_text())["permissions"]["deny"]
        assert "Task" in deny, deny


class TestNoProviderSpawnRaises:
    """Leg D1: a delivery spawn with no registered provider raises RuntimeError
    instead of falling through to the (deleted) Claude CLI docker run path."""

    @pytest.mark.asyncio
    async def test_no_provider_delivery_spawn_raises(self) -> None:
        orch = _orch()
        with (
            patch.object(orch, "_provider_for", return_value=None),
            pytest.raises(RuntimeError, match="No spawn backend"),
        ):
            await orch._spawn_container(_make_dev_config(), initial_prompt="x")


class TestFableModeHooksInjection:
    """Fable-mode hooks are additive to settings.json, gated by the flag."""

    def test_fable_hooks_absent_when_flag_disabled(self) -> None:
        with patch("robofleet.config.settings.fable_mode_enabled", False):
            orch = _orch()
            path = orch._generate_agent_settings(
                agent_id="be-dev-1",
                role="developer",
                workspace_path=_WS,
                cell_workspace_path=_CELL,
            )
        hooks = json.loads(Path(path).read_text())["hooks"]
        assert "SubagentStop" not in hooks
        stop_cmds = [h["command"] for g in hooks["Stop"] for h in g["hooks"]]
        assert not any("fable" in c for c in stop_cmds)

    def test_fable_hooks_present_when_flag_enabled(self) -> None:
        with patch("robofleet.config.settings.fable_mode_enabled", True):
            orch = _orch()
            path = orch._generate_agent_settings(
                agent_id="be-dev-1",
                role="developer",
                workspace_path=_WS,
                cell_workspace_path=_CELL,
            )
        hooks = json.loads(Path(path).read_text())["hooks"]
        stop_cmds = [h["command"] for g in hooks["Stop"] for h in g["hooks"]]
        assert stop_cmds[-1] == "/app/scripts/fable-stop-gate-hook.sh"  # appended last
        assert (
            stop_cmds[0] == "/app/scripts/stop-hook.sh"
        )  # RoboFleet's check still first
        subagent_cmds = [
            h["command"] for g in hooks["SubagentStop"] for h in g["hooks"]
        ]
        assert subagent_cmds == ["/app/scripts/fable-stop-gate-hook.sh subagent"]
        pretool_bash = [
            h["command"]
            for g in hooks["PreToolUse"]
            if g.get("matcher") == "Bash"
            for h in g["hooks"]
        ]
        assert "/app/scripts/bash-guard-hook.sh" in pretool_bash  # existing guard kept
        assert "/app/scripts/fable-bash-discipline-hook.sh" in pretool_bash
        posttool_bash = [
            h["command"]
            for g in hooks["PostToolUse"]
            if g.get("matcher") == "Bash"
            for h in g["hooks"]
        ]
        assert posttool_bash == ["/app/scripts/fable-honesty-nudge-hook.sh"]  # new

    def test_fable_hooks_off_leaves_hooks_dict_unchanged(self) -> None:
        """Regression guard: flag-off output equals a captured pre-Phase-2 baseline."""
        with patch("robofleet.config.settings.fable_mode_enabled", False):
            orch = _orch()
            path = orch._generate_agent_settings(
                agent_id="be-dev-1",
                role="developer",
                workspace_path=_WS,
                cell_workspace_path=_CELL,
            )
        hooks = json.loads(Path(path).read_text())["hooks"]
        assert set(hooks.keys()) == {
            "SessionStart",
            "PreToolUse",
            "PostToolUse",
            "Stop",
            "UserPromptSubmit",
            "PreCompact",
            "SessionEnd",
        }
