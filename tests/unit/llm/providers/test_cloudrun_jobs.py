"""Tests for the Cloud Run Jobs spawn backend."""

from unittest.mock import MagicMock

import pytest
from google.cloud import run_v2
from robofleet.llm.providers import cloudrun_jobs as mod


@pytest.mark.asyncio
async def test_spawn_submits_job_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = MagicMock()
    fake_op = MagicMock()
    # run_job's Operation has no .name; its metadata is the Execution.
    fake_op.metadata.name = (
        "projects/p/locations/e/jobs/robofleet-agent-x/executions/abc123"
    )
    fake_client.create_job = MagicMock(return_value=MagicMock())
    fake_client.run_job = MagicMock(return_value=fake_op)
    monkeypatch.setattr(mod, "_jobs_client", lambda: fake_client)
    monkeypatch.setattr(mod, "_rotate_secret", lambda _sid, _v: None)
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


@pytest.mark.asyncio
async def test_execution_name_prefers_operation_metadata() -> None:
    op = MagicMock()
    op.metadata.name = "projects/p/locations/r/jobs/j/executions/e1"
    client = MagicMock()
    assert await mod._execution_name(op, client, "projects/p/locations/r/jobs/j") == (
        "projects/p/locations/r/jobs/j/executions/e1"
    )
    client.get_job.assert_not_called()


@pytest.mark.asyncio
async def test_execution_name_falls_back_to_latest_created_execution() -> None:
    # A bare Operation (no usable metadata) -> ask the Job for its newest
    # execution; the field is a short id that must be re-qualified.
    op = object()
    client = MagicMock()
    client.get_job.return_value.latest_created_execution.name = "j-abc12"
    assert await mod._execution_name(op, client, "projects/p/locations/r/jobs/j") == (
        "projects/p/locations/r/jobs/j/executions/j-abc12"
    )


@pytest.mark.asyncio
async def test_execution_outcome_reads_completed_condition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _exe(state: int | None) -> MagicMock:
        exe = MagicMock()
        exe.completion_time = None if state is None else "2026-08-26T19:11:23Z"
        cond = MagicMock()
        cond.type_ = "Completed"
        cond.state = state
        ready = MagicMock()
        ready.type_ = "Started"
        ready.state = run_v2.Condition.State.CONDITION_SUCCEEDED
        exe.conditions = [ready, cond]
        return exe

    client = MagicMock()
    monkeypatch.setattr(mod, "_executions_client", lambda: client)
    provider = _provider()
    client.get_execution.return_value = _exe(None)
    assert await provider.execution_outcome("x") is None
    client.get_execution.return_value = _exe(run_v2.Condition.State.CONDITION_SUCCEEDED)
    assert await provider.execution_outcome("x") == 0
    client.get_execution.return_value = _exe(run_v2.Condition.State.CONDITION_FAILED)
    assert await provider.execution_outcome("x") == 1
