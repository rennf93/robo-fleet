"""Agent image resolution — local build vs. pre-built registry images.

``_qualify_agent_image`` decides what image name the orchestrator spawns (and
ensures). Empty registry/tag MUST return the bare name unchanged so the local
build flow and existing NAS deployment are untouched; a configured registry
switches every agent to the pre-built ``{registry}/robofleet-agent-*[:tag]``.

Delivery slugs (dev/qa/doc/pm/pr-reviewer/ux) no longer carry specialized
images after Leg D1 (the Claude CLI docker spawn path was stripped; ADK is the
delivery spawn path), so they fall back to AGENT_BASE_IMAGE. Only the
interactive persistent containers (intake/secretary) keep named images.
"""

from __future__ import annotations

import pytest
from robofleet.runtime import orchestrator as orch
from robofleet.runtime.orchestrator import INTAKE_AGENT_ID, SECRETARY_AGENT_ID


@pytest.mark.parametrize(
    ("registry", "tag", "bare", "expected"),
    [
        # Default: no registry, no tag -> bare name unchanged (local build).
        ("", "", "robofleet-agent-prompter", "robofleet-agent-prompter"),
        # Registry only -> qualified, implicit :latest.
        (
            "ghcr.io/rennf93",
            "",
            "robofleet-agent-prompter",
            "ghcr.io/rennf93/robofleet-agent-prompter",
        ),
        # Trailing slash on the registry is tolerated.
        (
            "ghcr.io/rennf93/",
            "latest",
            "robofleet-agent-prompter",
            "ghcr.io/rennf93/robofleet-agent-prompter:latest",
        ),
        # Docker Hub namespace + pinned version.
        (
            "docker.io/renzof93",
            "0.5.0",
            "robofleet-agent-base",
            "docker.io/renzof93/robofleet-agent-base:0.5.0",
        ),
        # Tag without registry is still applied (edge case, valid).
        ("", "latest", "robofleet-agent-secretary", "robofleet-agent-secretary:latest"),
    ],
)
def test_qualify_agent_image(
    monkeypatch: pytest.MonkeyPatch,
    registry: str,
    tag: str,
    bare: str,
    expected: str,
) -> None:
    monkeypatch.setattr(orch.settings, "agent_image_registry", registry)
    monkeypatch.setattr(orch.settings, "agent_image_tag", tag)
    assert orch._qualify_agent_image(bare) == expected


def test_get_agent_image_local_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orch.settings, "agent_image_registry", "")
    monkeypatch.setattr(orch.settings, "agent_image_tag", "")
    # Delivery slugs now fall back to AGENT_BASE_IMAGE (Leg D1: the Claude CLI
    # docker spawn path was stripped; ADK is the delivery spawn path).
    assert orch.get_agent_image("be-dev-1") == "robofleet-agent-base"
    assert orch.get_agent_image("pr-reviewer-1") == "robofleet-agent-base"
    # Interactive persistent containers keep their named images.
    assert orch.get_agent_image(INTAKE_AGENT_ID) == "robofleet-agent-prompter"
    assert orch.get_agent_image(SECRETARY_AGENT_ID) == "robofleet-agent-secretary"
    # A genuinely unknown agent id also falls back to the base image.
    assert orch.get_agent_image("nope-not-real") == "robofleet-agent-base"


def test_get_agent_image_registry_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orch.settings, "agent_image_registry", "ghcr.io/rennf93")
    monkeypatch.setattr(orch.settings, "agent_image_tag", "0.5.0")
    assert (
        orch.get_agent_image(INTAKE_AGENT_ID)
        == "ghcr.io/rennf93/robofleet-agent-prompter:0.5.0"
    )
    assert (
        orch.get_agent_image(SECRETARY_AGENT_ID)
        == "ghcr.io/rennf93/robofleet-agent-secretary:0.5.0"
    )
    # Delivery slugs fall back to the qualified base image in registry mode.
    assert (
        orch.get_agent_image("be-dev-1") == "ghcr.io/rennf93/robofleet-agent-base:0.5.0"
    )
