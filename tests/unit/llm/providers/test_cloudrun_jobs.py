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
    # A dev spawn resolves a Filestore workspace cwd, which the provider
    # refuses to set without the NFS volume (see the guard tests below).
    monkeypatch.setattr(mod.settings, "gcp_filestore_ip", "10.0.0.5")
    monkeypatch.setattr(mod.settings, "gcp_filestore_nfs_path", "/workspaces")

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
    # The workspace cwd rides the NFS volume onto the Job.
    assert container.working_dir.startswith("/data/workspaces/")
    assert create_req.job.template.template.volumes[0].nfs.server == "10.0.0.5"


def _provider() -> mod.CloudRunJobsProvider:
    return mod.CloudRunJobsProvider(host=MagicMock(), image="r/agent:latest")


def test_task_template_mounts_nfs_and_connector_for_workspace_cwd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mod.settings, "gcp_filestore_ip", "10.0.0.5")
    monkeypatch.setattr(mod.settings, "gcp_filestore_nfs_path", "/workspaces")
    monkeypatch.setattr(mod.settings, "workspaces_root", "/data/workspaces")
    monkeypatch.setattr(
        mod.settings, "gcp_vpc_connector_name", "projects/p/locations/r/connectors/c"
    )
    cwd = "/data/workspaces/proj/backend/be-dev-1/.worktrees/abc"

    template = _provider()._build_task_template([], cwd)

    container = template.containers[0]
    assert container.working_dir == cwd
    assert container.volume_mounts[0].mount_path == "/data/workspaces"
    assert template.volumes[0].nfs.server == "10.0.0.5"
    assert template.volumes[0].nfs.path == "/workspaces"
    assert template.vpc_access.connector == "projects/p/locations/r/connectors/c"


def test_task_template_refuses_workspace_cwd_without_nfs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A workingDir on the (unmounted) Filestore path makes Cloud Run fail the
    # container exec before the entrypoint runs: refuse at spawn instead.
    monkeypatch.setattr(mod.settings, "gcp_filestore_ip", "")
    monkeypatch.setattr(mod.settings, "gcp_filestore_nfs_path", "")

    with pytest.raises(mod.ProviderError, match="ROBOFLEET_GCP_FILESTORE_IP"):
        _provider()._build_task_template([], "/data/workspaces/x")

    # No workspace (coordination roles): still no volume, no error.
    template = _provider()._build_task_template([], None)
    assert not template.volumes
    assert not template.containers[0].working_dir
