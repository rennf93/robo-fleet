"""Interactive intake/secretary builders fork a GROK route onto the grok CLI.

A GROK route swaps the Gemini/ADK prompter/secretary image for the grok-CLI
image and the GEMINI_API_KEY env for the subscription auth mount + the
per-agent usage mount (no metered xAI key, no permission env - the driver
computes the grok permission flags). Every other provider keeps the
Gemini/ADK image and gets GEMINI_API_KEY + ROBOFLEET_AGENT_MODEL injected.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from robofleet.config import settings
from robofleet.llm.providers import grok as grok_provider
from robofleet.runtime.orchestrator import (
    GROK_PROMPTER_IMAGE,
    GROK_SECRETARY_IMAGE,
    AgentOrchestrator,
    _IntakeRunSpec,
    _SecretaryRunSpec,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

_HOSTS: dict[str, str | None] = {
    "claude": "/h/.claude",
    "prompt": "/h/p.md",
    "workspaces": "/h/ws",
    "grok_usage": "/h/gu/intake-1",
}


def _intake_spec(
    provider_type: str, *, base_url: str | None, token: str | None
) -> _IntakeRunSpec:
    is_grok = provider_type == "grok"
    return _IntakeRunSpec(
        container_name="robofleet-agent-intake-1",
        image=GROK_PROMPTER_IMAGE if is_grok else "robofleet-agent-gemini-prompter",
        hosts=_HOSTS,
        session_id="sess-1",
        cwd="/data/workspace",
        cli_model="grok-build",
        api_url="http://robofleet-orchestrator:8000",
        provider_base_url=base_url,
        provider_auth_token=token,
        provider_type=provider_type,
        model="grok-build" if is_grok else "",
    )


def test_intake_grok_uses_grok_cli_usage_mount_and_env() -> None:
    cmd = AgentOrchestrator._build_intake_run_cmd(
        _intake_spec("grok", base_url="https://api.x.ai/v1", token="xai-key")
    )
    # The per-agent usage dir is mounted so finalize reads usage.json back.
    assert "/h/gu/intake-1:/home/agent/.grok-usage" in cmd
    assert "ROBOFLEET_AGENT_MODEL=grok-build" in cmd
    assert "ROBOFLEET_GROK_USAGE_FILE=/home/agent/.grok-usage/usage.json" in cmd
    assert cmd[-1] == GROK_PROMPTER_IMAGE
    # No metered xAI key, no Anthropic mislabelling, no stale opencode contract.
    assert not any(c.startswith("XAI_") for c in cmd)
    assert not any(c.startswith("ANTHROPIC_") for c in cmd)
    assert not any(c.startswith("ROBOFLEET_GROK_VARIANT") for c in cmd)
    assert not any(c.startswith("ROBOFLEET_GROK_EDIT_PERMISSION") for c in cmd)
    assert "/home/agent/.local/share/opencode" not in " ".join(cmd)


def test_intake_grok_mounts_subscription_auth_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The auth mount is .exists()-guarded; point the host dir at a tmp ~/.grok
    # holding an auth.json so the mount is emitted.
    grok_dir = tmp_path / ".grok"
    grok_dir.mkdir()
    (grok_dir / "auth.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(grok_provider, "GROK_AUTH_HOST_PATH", str(grok_dir))

    cmd = AgentOrchestrator._build_intake_run_cmd(
        _intake_spec("grok", base_url="https://api.x.ai/v1", token="xai-key")
    )
    # directory mount (ro), not the single-file inode-pinning mount.
    assert f"{grok_dir}:/home/agent/.grok-auth-ro:ro" in cmd


def test_intake_anthropic_boots_gemini_driver_not_anthropic_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "gemini_api_key", "gem-key-anth")
    cmd = AgentOrchestrator._build_intake_run_cmd(
        _intake_spec("anthropic", base_url="https://api.anthropic.com", token="sk-ant")
    )
    joined = " ".join(cmd)
    # After D2 the non-grok path always boots the Gemini/ADK driver, so the
    # Anthropic creds are dead and GEMINI_API_KEY is injected instead.
    assert "GEMINI_API_KEY=gem-key-anth" in cmd
    assert "ROBOFLEET_AGENT_MODEL=gemini-3.5-flash" in cmd
    assert "ANTHROPIC_BASE_URL" not in joined
    assert "ANTHROPIC_AUTH_TOKEN" not in joined
    assert not any(c.startswith("XAI_") for c in cmd)
    assert not any(c.startswith("ROBOFLEET_GROK_USAGE_FILE") for c in cmd)
    assert cmd[-1] == "robofleet-agent-gemini-prompter"


def test_secretary_grok_uses_grok_cli_env_and_keeps_hmac() -> None:
    spec = _SecretaryRunSpec(
        container_name="robofleet-agent-secretary-1",
        image=GROK_SECRETARY_IMAGE,
        hosts={
            "claude": "/h/.claude",
            "prompt": "/h/p.md",
            "grok_usage": "/h/gu/sec-1",
        },
        session_id="sess-2",
        cwd="/app",
        cli_model="grok-build",
        api_url="http://robofleet-orchestrator:8000",
        agent_uuid="uuid-sec",
        agent_token="hmac-secretary",
        provider_base_url="https://api.x.ai/v1",
        provider_auth_token="xai-key",
        provider_type="grok",
        model="grok-build",
    )
    cmd = AgentOrchestrator._build_secretary_run_cmd(spec)
    assert "/h/gu/sec-1:/home/agent/.grok-usage" in cmd
    assert "ROBOFLEET_AGENT_MODEL=grok-build" in cmd
    # The HMAC identity the directive tools authenticate with survives.
    assert "ROBOFLEET_AGENT_TOKEN=hmac-secretary" in cmd
    assert cmd[-1] == GROK_SECRETARY_IMAGE
    assert not any(c.startswith("XAI_") for c in cmd)
    assert not any(c.startswith("ANTHROPIC_") for c in cmd)
