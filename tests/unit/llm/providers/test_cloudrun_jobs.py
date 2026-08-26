"""Tests for the Cloud Run Jobs spawn backend."""

from unittest.mock import MagicMock

import pytest
from robofleet.llm.providers import cloudrun_jobs as mod


@pytest.mark.asyncio
async def test_spawn_submits_job_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = MagicMock()
    fake_op = MagicMock()
    fake_op.name = "projects/p/locations/e/jobs/robofleet-agent-x/executions/abc123"
    fake_client.create_job = MagicMock(return_value=MagicMock())
    fake_client.run_job = MagicMock(return_value=fake_op)
    monkeypatch.setattr(mod, "_jobs_client", lambda: fake_client)

    provider = mod.CloudRunJobsProvider(
        host=MagicMock(),
        image="europe-west1-docker.pkg.dev/p/r/agent:latest",
    )
    cfg = MagicMock()
    cfg.agent_id = "be-dev-1"
    cfg.provider_type = "adk_cloud_run"

    result = await provider.spawn(cfg, initial_prompt="do the thing")

    assert result.instance_id.startswith("projects/")
    assert result.agent_state == "active"
    assert result.extra["model"] == "gemini-3.5-flash"
    job = result.extra["job"]
    assert isinstance(job, str)
    assert job.endswith("/jobs/robofleet-agent-be-dev-1")
    fake_client.create_job.assert_called_once()
    fake_client.run_job.assert_called_once()
    # manifest path unset -> no ROBOFLEET_TOOL_MANIFEST_PATH env on the job
    create_req = fake_client.create_job.call_args.kwargs["request"]
    container = create_req.job.template.template.containers[0]
    env_names = {e.name for e in container.env}
    assert "ROBOFLEET_TOOL_MANIFEST_PATH" not in env_names
    assert "ROBOFLEET_INITIAL_PROMPT" in env_names
