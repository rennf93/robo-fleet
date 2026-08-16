"""Cloud Run Jobs spawn backend for ADK+Gemini agents.

On GCP there is no Docker daemon, so the orchestrator cannot shell out to
``docker run``. Instead each agent runs as a Cloud Run Job execution: this
provider creates (or updates) the Job, then ``run_job`` starts an execution
and returns its fully-qualified name as the instance handle. The docker path
stays intact for local dev; this provider is only resolved for agents whose
``ModelProvider`` is ``ADK_CLOUD_RUN``.

The orchestrator writes the tool manifest (flow/do tools + system prompt) to a
local file and hands its ``Path`` here; this provider uploads it to GCS and
points the job at the ``gs://`` URI via ``ROBOFLEET_TOOL_MANIFEST_PATH``, so the
orchestrator itself never touches GCS.
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING, Any

import structlog
from google.cloud import run_v2

from robofleet.config import settings
from robofleet.llm.providers.base import AgentProvider, ProviderError, SpawnResult

if TYPE_CHECKING:
    from pathlib import Path

    from robofleet.models.runtime import OrchestratorAgentConfig as AgentConfig

# Model id ADK agents run on Cloud Run. The orchestrator does not pin a CLI
# here (no shell-out); this is the Gemini model id the agent container's ADK
# runtime is configured against.
_GEMINI_MODEL = "gemini-3.5-flash"

# Job max runtime. Cloud Run Jobs caps an execution at this wall-clock.
_JOB_TIMEOUT_SECONDS = 1800

# VpcAccess.Egress PRIVATE_RANGES_ONLY (the run_v2 proto enum has no
# pythonic alias; 2 is the numeric value of PRIVATE_RANGES_ONLY).
_VPC_EGRESS_PRIVATE_RANGES_ONLY = 2

_log = structlog.get_logger(__name__)


def _jobs_client() -> run_v2.JobsClient:
    return run_v2.JobsClient()


def _executions_client() -> run_v2.ExecutionsClient:
    return run_v2.ExecutionsClient()


def _parent() -> str:
    return f"projects/{settings.gcp_project_id}/locations/{settings.gcp_region}"


def _job_name(agent_id: str) -> str:
    slug = agent_id.replace("_", "-")
    return f"{_parent()}/jobs/{settings.gcp_cloud_run_agent_job_prefix}-{slug}"


async def _upload_manifest(path: Path | None, agent_id: str) -> str | None:
    """Upload the tool manifest to GCS, return its gs:// URI.

    None when there is no path, the file is missing, or no bucket is configured.
    """
    if path is None or not path.exists() or not settings.gcp_gcs_bucket:
        return None
    import google.cloud.storage

    bucket = google.cloud.storage.Client().bucket(settings.gcp_gcs_bucket)
    blob = bucket.blob(f"manifests/{agent_id}.json")
    await asyncio.to_thread(blob.upload_from_filename, str(path))
    return f"gs://{settings.gcp_gcs_bucket}/manifests/{agent_id}.json"


def _resolve_api_url() -> str:
    """Resolve the orchestrator URL the agent's gateway shim calls.

    Mirrors the MCP env block: settings.api_url wins (GCP sets it to the
    orchestrator's Cloud Run URL); ROBOFLEET_HOST_PROJECT_DIR -> the container
    hostname; else localhost. Unconditional: the agent needs gateway
    reachability regardless of deploy target.
    """
    if settings.api_url:
        return settings.api_url
    if os.environ.get("ROBOFLEET_HOST_PROJECT_DIR", ""):
        return "http://roboco-orchestrator:8000"
    return f"http://127.0.0.1:{settings.port}"


async def _append_git_token_env(
    env_vars: list[run_v2.EnvVar], config: AgentConfig
) -> None:
    """Append ROBOFLEET_GIT_TOKEN from the project's decrypted PAT when the task
    carries a git_context project slug. Best-effort: a missing/failed lookup
    skips the env var (the agent surfaces "ROBOFLEET_GIT_TOKEN not set" on push).
    """
    if not config.git_context or not config.git_context.project_slug:
        return
    from robofleet.db.base import get_db_context
    from robofleet.services.project import get_project_service

    try:
        async with get_db_context() as db:
            token = await get_project_service(db).get_decrypted_token_by_slug(
                config.git_context.project_slug
            )
    except Exception as exc:
        _log.warning(
            "git token lookup failed; agent will push without a PAT",
            project_slug=config.git_context.project_slug,
            error=str(exc),
        )
        return
    if token:
        env_vars.append(run_v2.EnvVar(name="ROBOFLEET_GIT_TOKEN", value=token))


class CloudRunJobsProvider(AgentProvider):
    """Spawn agents as Cloud Run Job executions."""

    def __init__(self, host: object, image: str | None = None) -> None:
        # ``host`` is accepted for ABC-construction parity with the docker
        # providers (which receive the docker host). Cloud Run has no host.
        self._host = host
        self._image = image or ""

    async def spawn(
        self,
        config: AgentConfig,
        initial_prompt: str | None = None,
        agent_settings_path: Path | None = None,
    ) -> SpawnResult:
        from robofleet.agents_config import (
            get_agent_role as _get_role,
        )
        from robofleet.agents_config import (
            get_agent_team as _get_team,
        )
        from robofleet.agents_config import (
            issue_agent_token,
        )
        from robofleet.seeds.initial_data import AGENT_UUIDS

        name = _job_name(config.agent_id)
        client = _jobs_client()

        # Agent identity: sign the HMAC token over the UUID (not the slug) so
        # the gateway's X-Agent-ID (Annotated[UUID, Header]) parses and the
        # token signature matches. Mirrors orchestrator._append_agent_auth_env.
        role = _get_role(config.agent_id)
        team = _get_team(config.agent_id) or ""
        agent_uuid = AGENT_UUIDS.get(config.agent_id, config.agent_id)
        token = issue_agent_token(
            agent_uuid,
            role,
            team,
            ttl_seconds=settings.agent_token_ttl_seconds,
        )

        # api_url resolution mirrors the MCP env block (orchestrator.py).
        api_url = _resolve_api_url()

        env_vars = [
            run_v2.EnvVar(name="ROBOFLEET_INITIAL_PROMPT", value=initial_prompt or ""),
            run_v2.EnvVar(name="ROBOFLEET_AGENT_ID", value=agent_uuid),
            run_v2.EnvVar(name="ROBOFLEET_AGENT_MODEL", value=_GEMINI_MODEL),
            run_v2.EnvVar(name="ROBOFLEET_AGENT_TOKEN", value=token),
            run_v2.EnvVar(name="ROBOFLEET_AGENT_ROLE", value=role),
            run_v2.EnvVar(name="ROBOFLEET_ORCHESTRATOR_URL", value=api_url),
            run_v2.EnvVar(name="ROBOFLEET_API_URL", value=api_url),
            run_v2.EnvVar(
                name="ROBOFLEET_FLOW_VERB_TIMEOUT_SECONDS",
                value=str(settings.flow_verb_timeout_seconds),
            ),
            run_v2.EnvVar(
                name="ROBOFLEET_FLOW_VERB_SLOW_TIMEOUT_SECONDS",
                value=str(settings.flow_verb_slow_timeout_seconds),
            ),
        ]
        # The orchestrator writes the ADK tool manifest to config.mcp_config_path
        # (via _generate_adk_manifest); upload THAT to GCS, not the Claude-Code
        # settings.json (agent_settings_path, irrelevant for ADK). The entrypoint
        # fetches it via ROBOFLEET_TOOL_MANIFEST_PATH.
        manifest_uri = await _upload_manifest(config.mcp_config_path, config.agent_id)
        if manifest_uri:
            env_vars.append(
                run_v2.EnvVar(name="ROBOFLEET_TOOL_MANIFEST_PATH", value=manifest_uri)
            )

        # ROBOFLEET_GIT_TOKEN: the ADK git_push tool (git_tools.py) reads it env
        # and pushes via the x-access-token extraheader against the remote, so
        # a task with a project needs the decrypted PAT. Best-effort: a
        # missing/failed lookup skips the env var (the agent surfaces a clear
        # "ROBOFLEET_GIT_TOKEN not set" on push, never a crash).
        await _append_git_token_env(env_vars, config)

        # Workspace cwd + ROBOFLEET_WORKSPACE_DIR env (developer / product_owner /
        # head_marketing / documenter). The git/file FunctionTools in
        # git_tools._worktree() read ROBOFLEET_WORKSPACE_DIR to resolve every
        # read_file / write_file / git op; setting both working_dir (so the
        # process cwd IS the workspace) and the env var (so the tools resolve
        # even if cwd drifts) keeps the two in lockstep. Roles without a
        # workspace (qa / cell_pm / main_pm / auditor / pr_reviewer) omit both:
        # git_tools falls back to cwd gracefully (Part 1). _resolve_workspace_cwd
        # is a staticmethod on AgentOrchestrator; lazy import avoids the
        # cloudrun_jobs -> orchestrator -> cloudrun_jobs circular import.
        from robofleet.runtime.orchestrator import AgentOrchestrator

        workspace_cwd = AgentOrchestrator._resolve_workspace_cwd(config)
        container_kwargs: dict[str, Any] = {"image": self._image, "env": env_vars}
        if workspace_cwd is not None:
            container_kwargs["working_dir"] = workspace_cwd
            env_vars.append(
                run_v2.EnvVar(name="ROBOFLEET_WORKSPACE_DIR", value=workspace_cwd)
            )
        volumes: list[run_v2.Volume] = []
        # Filestore NFS workspace volume (GCP only). Mounted at the workspaces
        # root so the agent's per-agent clone resolves to the shared Filestore.
        # Guarded: local-dev (ip/path empty) gets no volume, byte-for-byte
        # unchanged from the prior shape.
        if settings.gcp_filestore_ip and settings.gcp_filestore_nfs_path:
            container_kwargs["volume_mounts"] = [
                run_v2.VolumeMount(
                    mount_path=settings.workspaces_root,
                    name="filestore",
                )
            ]
            volumes.append(
                run_v2.Volume(
                    name="filestore",
                    nfs=run_v2.NFSVolumeSource(
                        server=settings.gcp_filestore_ip,
                        path=settings.gcp_filestore_nfs_path,
                        read_only=False,
                    ),
                )
            )

        template = run_v2.TaskTemplate(
            containers=[run_v2.Container(**container_kwargs)],
            timeout={"seconds": _JOB_TIMEOUT_SECONDS},
            volumes=volumes,
        )
        # VPC connector (GCP only): lets the Job reach Cloud SQL + Memorystore
        # on the roboco-net VPC. The v2-native VpcAccess.connector is the
        # equivalent of the v1 run.googleapis.com/vpc-access-connector
        # annotation used in the manual-deploy template.
        if settings.gcp_vpc_connector_name:
            template.vpc_access = run_v2.VpcAccess(
                connector=settings.gcp_vpc_connector_name,
                egress=_VPC_EGRESS_PRIVATE_RANGES_ONLY,
            )

        job = run_v2.Job(template=run_v2.ExecutionTemplate(template=template))
        # Idempotent create-or-update: create first, fall back to update if the
        # job already exists from a prior spawn of the same agent.
        try:
            req = run_v2.CreateJobRequest(
                parent=_parent(), job_id=name.split("/")[-1], job=job
            )
            await asyncio.to_thread(client.create_job, request=req)
        except Exception:
            update_job = run_v2.Job(name=name, template=job.template)
            req = run_v2.UpdateJobRequest(job=update_job)
            await asyncio.to_thread(client.update_job, request=req)
        op = await asyncio.to_thread(
            client.run_job, request=run_v2.RunJobRequest(name=name)
        )
        execution_name = getattr(op, "name", "") or f"{name}/executions/1"
        return SpawnResult(
            instance_id=execution_name,
            extra={"job": name, "model": _GEMINI_MODEL},
        )

    async def health_check(self, instance_id: str) -> bool:
        client = _executions_client()
        try:
            exe = await asyncio.to_thread(
                client.get_execution,
                request=run_v2.GetExecutionRequest(name=instance_id),
            )
            # Cloud Run v2 has no ExecutionStatus enum; an execution is alive
            # while completion_time is unset.
            return exe.completion_time is None
        except Exception:
            return False

    async def execution_outcome(self, instance_id: str) -> int | None:
        """Terminal outcome of a Cloud Run Job execution.

        Returns ``None`` while still running, ``0`` if the execution succeeded,
        ``1`` if it failed. Read from the Execution's ``conditions`` repeated
        field: the ``Ready`` condition's ``state`` is ``CONDITION_SUCCEEDED``
        on a clean finish and ``CONDITION_FAILED`` on a non-zero task exit. A
        completed execution with no Ready condition is treated as failed
        (safer; the prior behaviour treated every finish as a crash anyway).
        Field shape verified against the installed ``google-cloud-run`` proto:
        ``Execution.conditions`` (plural, repeated ``run_v2.Condition``),
        ``Condition.type_`` (Python alias for the ``type`` field), and
        ``Condition.State`` enum members
        ``CONDITION_SUCCEEDED`` / ``CONDITION_FAILED``.
        """
        client = _executions_client()
        exe = await asyncio.to_thread(
            client.get_execution,
            request=run_v2.GetExecutionRequest(name=instance_id),
        )
        if exe.completion_time is None:
            return None  # still running
        for cond in exe.conditions:
            if getattr(cond, "type_", "") == "Ready":
                if cond.state == run_v2.Condition.State.CONDITION_SUCCEEDED:
                    return 0
                if cond.state == run_v2.Condition.State.CONDITION_FAILED:
                    return 1
        return 1  # completed but no Ready condition -> treat as failed

    async def stop(self, instance_id: str, graceful: bool = True) -> None:
        client = _executions_client()
        try:
            await asyncio.to_thread(
                client.cancel_execution,
                request=run_v2.CancelExecutionRequest(name=instance_id),
            )
        except Exception as exc:
            raise ProviderError(
                f"failed to cancel execution {instance_id}", cause=exc
            ) from exc

    async def remove(self, instance_id: str) -> None:
        # Cloud Run Job executions are immutable and self-clean on completion;
        # the Job itself is reused across spawns of the same agent, so we do
        # not delete it here.
        return None
