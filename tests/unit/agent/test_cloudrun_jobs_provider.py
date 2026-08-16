"""Tests for CloudRunJobsProvider: env, volume, VPC, identity wiring.

Asserts the constructed Cloud Run Job carries the full agent-identity env
surface (HMAC token signed over the UUID, not the slug), the Filestore NFS
workspace volume + VPC connector when GCP fields are armed, and the
ROBOFLEET_GIT_TOKEN from the project's decrypted PAT. Uses real ``run_v2``
objects (no GCP call: only the JobsClient is faked) so the assertions inspect
the exact protobuf the provider would submit.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from robofleet.llm.providers.cloudrun_jobs import CloudRunJobsProvider
from robofleet.models.runtime import OrchestratorAgentConfig as AgentConfig
from robofleet.models.runtime import SpawnGitContext

if TYPE_CHECKING:
    from google.cloud import run_v2


async def _noop_manifest(_path: Path | None, _slug: str) -> None:
    """Stand-in for _upload_manifest: no GCS upload in tests."""
    return None


# A stable slug -> UUID pair the docker path also uses (seeds map shape).
_SLUG = "be-dev-1"
_UUID = "11111111-2222-3333-4444-555555555555"
_ROLE = "developer"
_TEAM = "backend"
_TOKEN = "signed-hmac-token"


class _FakeOp:
    name: str = "projects/test/locations/us/jobs/robofleet-agent-be-dev-1/executions/1"


class _FakeJobsClient:
    """Captures the CreateJobRequest so the test inspects the Job protobuf."""

    def __init__(self) -> None:
        self.captured: run_v2.CreateJobRequest | None = None

    def create_job(self, *, request: run_v2.CreateJobRequest) -> None:
        self.captured = request

    def update_job(self, *, request: run_v2.UpdateJobRequest) -> None:
        self.captured = request

    def run_job(self, *, request: run_v2.RunJobRequest) -> _FakeOp:
        return _FakeOp()


def _env_map(job: run_v2.Job) -> dict[str, str]:
    envs = job.template.template.containers[0].env
    return {e.name: e.value for e in envs}


def _config(
    git_context: SpawnGitContext | None = None,
    mcp_config_path: Path | None = None,
) -> AgentConfig:
    return AgentConfig(
        agent_id=_SLUG,
        blueprint_path=Path("/app/blueprint.md"),
        git_context=git_context,
        mcp_config_path=mcp_config_path,
    )


def _patch_identity(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Patch identity helpers + AGENT_UUIDS; return the call-args recorder."""
    calls: dict[str, str] = {}

    def _fake_issue(uuid: str, role: str, team: str, *, ttl_seconds: int) -> str:
        calls["uuid"] = uuid
        calls["role"] = role
        calls["team"] = team
        return _TOKEN

    monkeypatch.setattr("robofleet.agents_config.issue_agent_token", _fake_issue)
    monkeypatch.setattr("robofleet.agents_config.get_agent_role", lambda _s: _ROLE)
    monkeypatch.setattr("robofleet.agents_config.get_agent_team", lambda _s: _TEAM)
    monkeypatch.setattr("robofleet.seeds.initial_data.AGENT_UUIDS", {_SLUG: _UUID})
    return calls


def _patch_client(monkeypatch: pytest.MonkeyPatch) -> _FakeJobsClient:
    fake = _FakeJobsClient()
    monkeypatch.setattr(
        "robofleet.llm.providers.cloudrun_jobs._jobs_client", lambda: fake
    )
    monkeypatch.setattr(
        "robofleet.llm.providers.cloudrun_jobs._upload_manifest",
        _noop_manifest,
    )
    return fake


@pytest.mark.asyncio
async def test_spawn_env_identity_token_signed_over_uuid(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Full env surface present; AGENT_ID is the UUID; token signed over UUID."""
    monkeypatch.setattr("robofleet.config.settings.api_url", "http://orch:8000")
    monkeypatch.setattr("robofleet.config.settings.flow_verb_timeout_seconds", 120.0)
    monkeypatch.setattr("robofleet.config.settings.flow_verb_slow_timeout_seconds", 900)
    monkeypatch.setattr("robofleet.config.settings.gcp_project_id", "test-proj")
    monkeypatch.setattr("robofleet.config.settings.gcp_region", "us-central1")
    calls = _patch_identity(monkeypatch)
    fake = _patch_client(monkeypatch)

    provider = CloudRunJobsProvider(host=object(), image="gcr.io/robofleet/agent")
    await provider.spawn(_config(), initial_prompt="do the work")

    assert fake.captured is not None
    env = _env_map(fake.captured.job)
    # Token issued over the UUID, not the slug.
    assert calls["uuid"] == _UUID
    assert calls["role"] == _ROLE
    assert calls["team"] == _TEAM
    # AGENT_ID is the UUID (gateway X-Agent-ID is Annotated[UUID, Header]).
    assert env["ROBOFLEET_AGENT_ID"] == _UUID
    assert env["ROBOFLEET_AGENT_TOKEN"] == _TOKEN
    assert env["ROBOFLEET_AGENT_ROLE"] == _ROLE
    assert env["ROBOFLEET_ORCHESTRATOR_URL"] == "http://orch:8000"
    assert env["ROBOFLEET_API_URL"] == "http://orch:8000"
    assert env["ROBOFLEET_FLOW_VERB_TIMEOUT_SECONDS"] == "120.0"
    assert env["ROBOFLEET_FLOW_VERB_SLOW_TIMEOUT_SECONDS"] == "900"
    # Existing 4 env vars still present.
    assert env["ROBOFLEET_INITIAL_PROMPT"] == "do the work"
    assert env["ROBOFLEET_AGENT_MODEL"] == "gemini-3.5-flash"
    # No git context -> no ROBOFLEET_GIT_TOKEN.
    assert "ROBOFLEET_GIT_TOKEN" not in env


@pytest.mark.asyncio
async def test_spawn_filestore_volume_and_vpc_when_gcp_armed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Filestore NFS volume mounted at workspaces root + VpcAccess set."""
    monkeypatch.setattr("robofleet.config.settings.api_url", "http://orch:8000")
    monkeypatch.setattr("robofleet.config.settings.gcp_project_id", "test-proj")
    monkeypatch.setattr("robofleet.config.settings.gcp_region", "us-central1")
    monkeypatch.setattr(
        "robofleet.config.settings.workspaces_root", "/mnt/fileshare/workspaces"
    )
    monkeypatch.setattr("robofleet.config.settings.gcp_filestore_ip", "10.0.0.5")
    monkeypatch.setattr(
        "robofleet.config.settings.gcp_filestore_nfs_path", "/workspaces"
    )
    monkeypatch.setattr(
        "robofleet.config.settings.gcp_vpc_connector_name", "robofleet-connector"
    )
    _patch_identity(monkeypatch)
    fake = _patch_client(monkeypatch)

    provider = CloudRunJobsProvider(host=object(), image="gcr.io/robofleet/agent")
    await provider.spawn(_config(), initial_prompt="do the work")

    assert fake.captured is not None
    tmpl = fake.captured.job.template.template
    container = tmpl.containers[0]
    # Volume mount at the workspaces root, read-write (default).
    assert container.volume_mounts[0].mount_path == "/mnt/fileshare/workspaces"
    assert container.volume_mounts[0].name == "filestore"
    # NFS volume present with the configured server + path.
    vol = tmpl.volumes[0]
    assert vol.name == "filestore"
    assert vol.nfs.server == "10.0.0.5"
    assert vol.nfs.path == "/workspaces"
    assert vol.nfs.read_only is False
    # VPC connector wired (v2-native VpcAccess, equivalent of the v1 annotation).
    assert tmpl.vpc_access.connector == "robofleet-connector"


@pytest.mark.asyncio
async def test_spawn_no_volume_vpc_when_gcp_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Local-dev: no Filestore volume, no VpcAccess when GCP fields empty."""
    monkeypatch.setattr("robofleet.config.settings.api_url", None)
    monkeypatch.setattr("robofleet.config.settings.gcp_project_id", "test-proj")
    monkeypatch.setattr("robofleet.config.settings.gcp_region", "us-central1")
    monkeypatch.setattr("robofleet.config.settings.gcp_filestore_ip", "")
    monkeypatch.setattr("robofleet.config.settings.gcp_filestore_nfs_path", "")
    monkeypatch.setattr("robofleet.config.settings.gcp_vpc_connector_name", "")
    _patch_identity(monkeypatch)
    fake = _patch_client(monkeypatch)

    provider = CloudRunJobsProvider(host=object(), image="gcr.io/robofleet/agent")
    await provider.spawn(_config(), initial_prompt="do the work")

    assert fake.captured is not None
    tmpl = fake.captured.job.template.template
    assert list(tmpl.volumes) == []
    assert container_has_no_mounts(tmpl.containers[0])
    # api_url falls back to localhost:port (no PROJECT_HOST_PATH in test env).
    env = _env_map(fake.captured.job)
    assert env["ROBOFLEET_ORCHESTRATOR_URL"].startswith("http://127.0.0.1:")


def container_has_no_mounts(container: run_v2.Container) -> bool:
    return len(list(container.volume_mounts)) == 0


@pytest.mark.asyncio
async def test_spawn_wires_git_token_from_project_pat(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """ROBOFLEET_GIT_TOKEN set from the project's decrypted PAT when git_context
    carries a project slug (the ADK git_push tool reads it directly)."""

    class _FakeProjectService:
        async def get_decrypted_token_by_slug(self, slug: str) -> str | None:
            assert slug == "roboco"
            return "ghp_decrypted_pat"

    class _FakeDbContext:
        async def __aenter__(self) -> Any:
            return None

        async def __aexit__(self, *exc: object) -> None:
            return None

    monkeypatch.setattr("robofleet.config.settings.api_url", "http://orch:8000")
    monkeypatch.setattr("robofleet.config.settings.gcp_project_id", "test-proj")
    monkeypatch.setattr("robofleet.config.settings.gcp_region", "us-central1")
    monkeypatch.setattr("robofleet.db.base.get_db_context", _FakeDbContext)
    monkeypatch.setattr(
        "robofleet.services.project.get_project_service",
        lambda _db: _FakeProjectService(),
    )
    _patch_identity(monkeypatch)
    fake = _patch_client(monkeypatch)

    provider = CloudRunJobsProvider(host=object(), image="gcr.io/robofleet/agent")
    await provider.spawn(
        _config(git_context=SpawnGitContext(project_slug="roboco")),
        initial_prompt="do the work",
    )

    assert fake.captured is not None
    env = _env_map(fake.captured.job)
    assert env["ROBOFLEET_GIT_TOKEN"] == "ghp_decrypted_pat"


@pytest.mark.asyncio
async def test_spawn_no_git_token_when_project_has_no_pat(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A project with no PAT (get_decrypted_token_by_slug -> None) skips the
    env var rather than injecting an empty value."""

    class _FakeProjectService:
        async def get_decrypted_token_by_slug(self, slug: str) -> str | None:
            return None

    class _FakeDbContext:
        async def __aenter__(self) -> Any:
            return None

        async def __aexit__(self, *exc: object) -> None:
            return None

    monkeypatch.setattr("robofleet.config.settings.api_url", "http://orch:8000")
    monkeypatch.setattr("robofleet.config.settings.gcp_project_id", "test-proj")
    monkeypatch.setattr("robofleet.config.settings.gcp_region", "us-central1")
    monkeypatch.setattr("robofleet.db.base.get_db_context", _FakeDbContext)
    monkeypatch.setattr(
        "robofleet.services.project.get_project_service",
        lambda _db: _FakeProjectService(),
    )
    _patch_identity(monkeypatch)
    fake = _patch_client(monkeypatch)

    provider = CloudRunJobsProvider(host=object(), image="gcr.io/robofleet/agent")
    await provider.spawn(
        _config(git_context=SpawnGitContext(project_slug="empty-project")),
        initial_prompt="do the work",
    )

    assert fake.captured is not None
    env = _env_map(fake.captured.job)
    assert "ROBOFLEET_GIT_TOKEN" not in env


@pytest.mark.asyncio
async def test_spawn_sets_working_dir_and_workspace_env_for_developer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Developer role: container working_dir + ROBOFLEET_WORKSPACE_DIR env set to
    _resolve_workspace_cwd's path (clone root when no task branch). The ADK
    git/file tools read ROBOFLEET_WORKSPACE_DIR; setting both working_dir (process
    cwd IS the workspace) and the env var keeps them in lockstep."""
    monkeypatch.setattr("robofleet.config.settings.api_url", "http://orch:8000")
    monkeypatch.setattr("robofleet.config.settings.gcp_project_id", "test-proj")
    monkeypatch.setattr("robofleet.config.settings.gcp_region", "us-central1")
    _patch_identity(monkeypatch)
    # _resolve_workspace_cwd reads the orchestrator module's module-level
    # get_agent_role / get_agent_team (imported at top of orchestrator.py),
    # not the lazy in-function import the provider's spawn uses.
    monkeypatch.setattr(
        "robofleet.runtime.orchestrator.get_agent_role", lambda _s: _ROLE
    )
    monkeypatch.setattr(
        "robofleet.runtime.orchestrator.get_agent_team", lambda _s: _TEAM
    )
    fake = _patch_client(monkeypatch)

    provider = CloudRunJobsProvider(host=object(), image="gcr.io/robofleet/agent")
    await provider.spawn(
        _config(git_context=SpawnGitContext(project_slug="roboco")),
        initial_prompt="do the work",
    )

    assert fake.captured is not None
    container = fake.captured.job.template.template.containers[0]
    expected = "/data/workspaces/roboco/backend/be-dev-1"
    assert container.working_dir == expected
    env = _env_map(fake.captured.job)
    assert env["ROBOFLEET_WORKSPACE_DIR"] == expected


@pytest.mark.asyncio
async def test_spawn_omits_working_dir_and_workspace_env_for_qa(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """QA role (no workspace): neither working_dir nor ROBOFLEET_WORKSPACE_DIR is
    set. git_tools._worktree falls back to the process cwd (Part 1), so a
    no-workspace role never needs the env var."""
    monkeypatch.setattr("robofleet.config.settings.api_url", "http://orch:8000")
    monkeypatch.setattr("robofleet.config.settings.gcp_project_id", "test-proj")
    monkeypatch.setattr("robofleet.config.settings.gcp_region", "us-central1")
    monkeypatch.setattr("robofleet.agents_config.get_agent_role", lambda _s: "qa")
    monkeypatch.setattr("robofleet.agents_config.get_agent_team", lambda _s: _TEAM)
    monkeypatch.setattr(
        "robofleet.runtime.orchestrator.get_agent_role", lambda _s: "qa"
    )
    monkeypatch.setattr(
        "robofleet.runtime.orchestrator.get_agent_team", lambda _s: _TEAM
    )
    monkeypatch.setattr("robofleet.seeds.initial_data.AGENT_UUIDS", {_SLUG: _UUID})

    def _qa_token(_uuid: str, _role: str, _team: str, *, ttl_seconds: int) -> str:
        return _TOKEN

    monkeypatch.setattr("robofleet.agents_config.issue_agent_token", _qa_token)
    fake = _patch_client(monkeypatch)

    provider = CloudRunJobsProvider(host=object(), image="gcr.io/robofleet/agent")
    await provider.spawn(
        _config(git_context=SpawnGitContext(project_slug="roboco")),
        initial_prompt="do the work",
    )

    assert fake.captured is not None
    container = fake.captured.job.template.template.containers[0]
    assert not container.working_dir
    env = _env_map(fake.captured.job)
    assert "ROBOFLEET_WORKSPACE_DIR" not in env
