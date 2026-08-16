"""Self-heal telemetry source — CI conclusion normalized to samples.

The GitHub-CI source watches ONLY RoboCo's own project
(``settings.self_heal_project_slug``): a failing run is a breaching sample, a
passing run a non-breaching one, and no target / no run yields nothing. It is
read-only and never raises.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from roboco.config import settings as cfg
from roboco.services.git import GitService
from roboco.services.telemetry import GitHubCITelemetrySource


def _ci(conclusion: str) -> dict[str, str]:
    return {
        "conclusion": conclusion,
        "head_sha": "abc123",
        "run_url": "https://github.com/x/roboco/actions/runs/1",
        "run_name": "CI",
        "branch": "master",
        "completed_at": "2026-06-17T00:00:00Z",
    }


@pytest.mark.asyncio
async def test_no_target_yields_no_samples(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "self_heal_project_slug", "")
    assert await GitHubCITelemetrySource(MagicMock()).fetch() == []


@pytest.mark.asyncio
async def test_failing_ci_is_a_breach(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "self_heal_project_slug", "roboco")
    monkeypatch.setattr(
        GitService, "get_latest_ci_conclusion", AsyncMock(return_value=_ci("failure"))
    )
    samples = await GitHubCITelemetrySource(MagicMock()).fetch()
    assert len(samples) == 1
    sample = samples[0]
    assert sample.is_breach is True
    assert sample.repo_hint == "roboco"
    assert sample.signal_name == "ci_conclusion:roboco"
    assert "failure" in sample.detail
    assert sample.raw_ref.endswith("/runs/1")


@pytest.mark.asyncio
async def test_passing_ci_is_not_a_breach(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "self_heal_project_slug", "roboco")
    monkeypatch.setattr(
        GitService, "get_latest_ci_conclusion", AsyncMock(return_value=_ci("success"))
    )
    samples = await GitHubCITelemetrySource(MagicMock()).fetch()
    assert len(samples) == 1
    assert samples[0].is_breach is False


@pytest.mark.asyncio
async def test_cancelled_run_is_not_a_breach(monkeypatch: pytest.MonkeyPatch) -> None:
    # A cancelled run is not a failing build — it must not count as a regression.
    monkeypatch.setattr(cfg, "self_heal_project_slug", "roboco")
    monkeypatch.setattr(
        GitService, "get_latest_ci_conclusion", AsyncMock(return_value=_ci("cancelled"))
    )
    samples = await GitHubCITelemetrySource(MagicMock()).fetch()
    assert len(samples) == 1
    assert samples[0].is_breach is False


@pytest.mark.asyncio
async def test_no_run_yields_no_samples(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "self_heal_project_slug", "roboco")
    monkeypatch.setattr(
        GitService, "get_latest_ci_conclusion", AsyncMock(return_value=None)
    )
    assert await GitHubCITelemetrySource(MagicMock()).fetch() == []
