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
import contextlib
import os
from typing import TYPE_CHECKING, Any

import structlog
from google.api_core.exceptions import AlreadyExists
from google.cloud import run_v2, secretmanager

from robofleet.config import settings
from robofleet.llm.providers.base import AgentProvider, ProviderError, SpawnResult

if TYPE_CHECKING:
    from pathlib import Path

    from robofleet.models.runtime import OrchestratorAgentConfig as AgentConfig

# Model id ADK agents run on Cloud Run. The orchestrator does not pin a CLI
# here (no shell-out); this is the Gemini model id the agent container's ADK
# runtime is configured against.
# gemini-3.5-flash is the hackathon-required model (Gemini 3.5+ via Vertex AI).
# Its canonical Vertex endpoint is the GLOBAL location (regional availability
# is preview and flipped 404<->200 day to day during Aug 2026), so the deploy
# points the Vertex MODEL location at global via gcp_vertex_model_location,
# while the Cloud Run Job region (gcp_region) stays a real region. Overridable
# per-spawn via ROBOFLEET_AGENT_MODEL.
_GEMINI_MODEL = os.environ.get("ROBOFLEET_AGENT_MODEL_DEFAULT", "gemini-3.5-flash")

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


def _secrets_client() -> secretmanager.SecretManagerServiceClient:
    return secretmanager.SecretManagerServiceClient()


def _rotate_secret(secret_id: str, value: str) -> None:
    """Store ``value`` as the only enabled version of ``secret_id``.

    Creates the secret on first use, adds a fresh version, then destroys every
    older enabled version so a leaked handle cannot replay a previous token.
    ponytail: versions are never pruned on retirement; the next spawn of the
    same agent rotates them, which is enough for one-secret-per-agent.
    """
    client = _secrets_client()
    parent = f"projects/{settings.gcp_project_id}"
    name = f"{parent}/secrets/{secret_id}"
    with contextlib.suppress(AlreadyExists):
        client.create_secret(
            request={
                "parent": parent,
                "secret_id": secret_id,
                "secret": {"replication": {"automatic": {}}},
            }
        )
    new = client.add_secret_version(
        request={"parent": name, "payload": {"data": value.encode()}}
    )
    for version in client.list_secret_versions(
        request={"parent": name, "filter": "state:ENABLED"}
    ):
        if version.name != new.name:
            client.destroy_secret_version(request={"name": version.name})


async def _secret_env(
    name: str, value: str, agent_id: str, suffix: str
) -> run_v2.EnvVar:
    """An env var carrying a secret: a Secret Manager reference on GCP.

    A plain ``value`` on a Cloud Run Job is readable by any project viewer in
    the console (the execution's Variables tab), so on GCP the value goes
    into a per-agent secret (rotated every spawn) and the Job references it;
    Cloud Run resolves ``latest`` when the execution starts. Only a deploy
    with no GCP project (local dev) keeps the plain value.
    """
    if not settings.gcp_project_id:
        return run_v2.EnvVar(name=name, value=value)
    slug = agent_id.replace("_", "-")
    secret_id = f"{settings.gcp_secret_manager_prefix}-agent-{slug}-{suffix}"
    try:
        await asyncio.to_thread(_rotate_secret, secret_id, value)
    except Exception as exc:
        raise ProviderError(f"could not store {name} in Secret Manager: {exc}") from exc
    return run_v2.EnvVar(
        name=name,
        value_source=run_v2.EnvVarSource(
            secret_key_ref=run_v2.SecretKeySelector(secret=secret_id, version="latest")
        ),
    )


async def _execution_name(op: Any, client: run_v2.JobsClient, job_name: str) -> str:
    """Resolve the full execution resource name a ``run_job`` call started.

    ``run_job`` returns a long-running Operation whose ``metadata`` IS the
    ``run_v2.Execution`` (the Operation object itself has no ``name``; the
    earlier ``getattr(op, "name", "")`` was always empty and left a
    placeholder ``.../executions/1`` handle behind, so every later
    ``health_check`` / ``execution_outcome`` hit a non-existent execution and
    the orchestrator never retired the instance). Falls back to the Job's
    ``latest_created_execution`` (a short id) when the metadata is missing.
    """
    meta = getattr(op, "metadata", None)
    name = getattr(meta, "name", None)
    if isinstance(name, str) and name.startswith("projects/"):
        return name
    job = await asyncio.to_thread(
        client.get_job, request=run_v2.GetJobRequest(name=job_name)
    )
    short = getattr(getattr(job, "latest_created_execution", None), "name", "")
    if isinstance(short, str) and short:
        return (
            short if short.startswith("projects/") else f"{job_name}/executions/{short}"
        )
    raise ProviderError(f"could not resolve the execution started for {job_name}")


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
        return "http://robofleet-orchestrator:8000"
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
        env_vars.append(
            await _secret_env(
                "ROBOFLEET_GIT_TOKEN", token, config.agent_id, "git-token"
            )
        )


class CloudRunJobsProvider(AgentProvider):
    """Spawn agents as Cloud Run Job executions."""

    def __init__(self, host: object, image: str | None = None) -> None:
        # ``host`` is accepted for ABC-construction parity with the docker
        # providers (which receive the docker host). Cloud Run has no host.
        self._host = host
        self._image = image or ""

    async def _spawn_env_vars(
        self,
        config: AgentConfig,
        initial_prompt: str | None,
        workspace_cwd: str | None,
    ) -> list[run_v2.EnvVar]:
        """Build the full Cloud Run Job env var list for ``config``.

        Resolves agent identity (role/team/UUID, the HMAC token signed over the
        UUID not the slug so the gateway's X-Agent-ID parses) and the orchestrator
        api_url, then conditionally appends the Gemini API key, the uploaded
        tool manifest URI, the decrypted git PAT, and ROBOFLEET_WORKSPACE_DIR
        for workspace roles. Best-effort throughout: a missing lookup skips the
        env var rather than crashing spawn.
        """
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
        api_url = _resolve_api_url()

        env_vars = [
            run_v2.EnvVar(name="ROBOFLEET_INITIAL_PROMPT", value=initial_prompt or ""),
            run_v2.EnvVar(name="ROBOFLEET_AGENT_ID", value=agent_uuid),
            run_v2.EnvVar(name="ROBOFLEET_AGENT_MODEL", value=_GEMINI_MODEL),
            await _secret_env(
                "ROBOFLEET_AGENT_TOKEN", token, config.agent_id, "agent-token"
            ),
            run_v2.EnvVar(name="ROBOFLEET_AGENT_ROLE", value=role),
            # The token is HMAC-signed over (id, role, team), and the gateway
            # verifier checks the X-Agent-* headers match the values embedded
            # in the token. The shim only sends X-Agent-Team when this env is
            # set, so omitting it makes every verb 401 with "Header values do
            # not match" (team "" != the signed team) with no other symptom.
            run_v2.EnvVar(name="ROBOFLEET_AGENT_TEAM", value=team),
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
        # Model auth. Two paths:
        # ① Vertex AI (preferred on GCP): ADK's google.genai.Client auto-detects
        #   Vertex when GOOGLE_GENAI_USE_VERTEXAI=1 plus project/location are set,
        #   authenticating via the Job's runtime service account ADC (no API key),
        #   so the agent bills the project's GCP credit instead of a separate
        #   AI Studio prepayment that can deplete. aiplatform.googleapis.com must
        #   be enabled and the runtime SA must hold a Vertex User role.
        # ② Gemini API key fallback (local dev / non-Vertex): ADK's Client reads
        #   GEMINI_API_KEY from the environment. The orchestrator holds it as
        #   ROBOFLEET_GEMINI_API_KEY (a Cloud Run env-secret backed by Secret
        #   Manager secret robofleet-gemini-api-key) and forwards it here under
        #   the bare name genai expects.
        if settings.gcp_project_id:
            env_vars.append(run_v2.EnvVar(name="GOOGLE_GENAI_USE_VERTEXAI", value="1"))
            env_vars.append(
                run_v2.EnvVar(
                    name="GOOGLE_CLOUD_PROJECT", value=settings.gcp_project_id
                )
            )
            env_vars.append(
                run_v2.EnvVar(
                    name="GOOGLE_CLOUD_LOCATION",
                    # The Vertex MODEL location (where the LLM is served), not
                    # the Cloud Run Job region (gcp_region, which must stay a
                    # real region). gemini-3.5-flash is global-only, so the
                    # deploy sets gcp_vertex_model_location=global; unset falls
                    # back to the Job region for regional models.
                    value=(
                        settings.gcp_vertex_model_location
                        or settings.gcp_region
                        or "us-central1"
                    ),
                )
            )
        elif settings.gemini_api_key:
            env_vars.append(
                await _secret_env(
                    "GEMINI_API_KEY",
                    settings.gemini_api_key,
                    config.agent_id,
                    "gemini-api-key",
                )
            )
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

        # Setting both working_dir (so the process cwd IS the workspace) and
        # the env var (so the tools resolve even if cwd drifts) keeps the two
        # in lockstep. Roles without a workspace omit both: git_tools falls
        # back to cwd gracefully (Part 1).
        if workspace_cwd is not None:
            env_vars.append(
                run_v2.EnvVar(name="ROBOFLEET_WORKSPACE_DIR", value=workspace_cwd)
            )
        return env_vars

    def _build_task_template(
        self, env_vars: list[run_v2.EnvVar], workspace_cwd: str | None
    ) -> run_v2.TaskTemplate:
        """Assemble the TaskTemplate (container, volumes, VPC connector)."""
        container_kwargs: dict[str, Any] = {"image": self._image, "env": env_vars}
        nfs_armed = bool(settings.gcp_filestore_ip and settings.gcp_filestore_nfs_path)
        if workspace_cwd is not None:
            # The workspace lives on the shared Filestore mount. Without the
            # NFS volume the cwd does not exist inside the Job container, and
            # Cloud Run fails the exec BEFORE the entrypoint runs ("Application
            # exec likely failed", zero output, no crash dump, no diag blob).
            # Fail loud at spawn instead of burning a silent retry loop.
            if not nfs_armed:
                raise ProviderError(
                    f"workspace cwd {workspace_cwd!r} needs the Filestore NFS "
                    "volume: set ROBOFLEET_GCP_FILESTORE_IP and "
                    "ROBOFLEET_GCP_FILESTORE_NFS_PATH on the orchestrator"
                )
            container_kwargs["working_dir"] = workspace_cwd
        # Cloud Run Jobs default to 512MiB memory when no limits are set. The
        # ADK runtime imports google-adk + google-genai + google-cloud-storage
        # plus the robofleet gateway shim (which pulls the full service graph),
        # and that import set OOMs at 512MiB before main() reaches its first
        # except handler: the container is SIGKILLed, so no crash dump and no
        # usage post land (out_tokens=0, NonZeroExitCode, no diagnostic). 2Gi
        # matches the orchestrator's proven-working envelope.
        # ponytail: fixed default; add a gcp_agent_memory setting if a fleet
        # ever needs per-role tuning.
        container_kwargs["resources"] = run_v2.ResourceRequirements(
            limits={"cpu": "1000m", "memory": "2Gi"}
        )
        volumes: list[run_v2.Volume] = []
        # Filestore NFS workspace volume (GCP only). Mounted at the workspaces
        # root so the agent's per-agent clone resolves to the shared Filestore.
        # Guarded: local-dev (ip/path empty) gets no volume, byte-for-byte
        # unchanged from the prior shape.
        if nfs_armed:
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
            # No Cloud Run-level retry: a retried task re-runs the whole agent
            # from scratch (full model spend again) with no orchestrator
            # bookkeeping; the respawn breaker is the only retry path.
            max_retries=0,
        )
        # VPC connector (GCP only): lets the Job reach Cloud SQL + Memorystore
        # on the robofleet-net VPC. The v2-native VpcAccess.connector is the
        # equivalent of the v1 run.googleapis.com/vpc-access-connector
        # annotation used in the manual-deploy template.
        if settings.gcp_vpc_connector_name:
            template.vpc_access = run_v2.VpcAccess(
                connector=settings.gcp_vpc_connector_name,
                egress=_VPC_EGRESS_PRIVATE_RANGES_ONLY,
            )
        return template

    @staticmethod
    async def _create_or_update_job(
        client: run_v2.JobsClient, name: str, job: run_v2.Job
    ) -> None:
        """Idempotent create-or-update: create first, fall back to update if the
        job already exists from a prior spawn of the same agent.
        """
        try:
            req = run_v2.CreateJobRequest(
                parent=_parent(), job_id=name.rsplit("/", maxsplit=1)[-1], job=job
            )
            await asyncio.to_thread(client.create_job, request=req)
        except Exception:
            update_job = run_v2.Job(name=name, template=job.template)
            req = run_v2.UpdateJobRequest(job=update_job)
            await asyncio.to_thread(client.update_job, request=req)

    async def spawn(
        self,
        config: AgentConfig,
        initial_prompt: str | None = None,
        agent_settings_path: Path | None = None,
    ) -> SpawnResult:
        name = _job_name(config.agent_id)
        client = _jobs_client()

        # _resolve_workspace_cwd is a staticmethod on AgentOrchestrator; lazy
        # import avoids the cloudrun_jobs -> orchestrator -> cloudrun_jobs
        # circular import.
        from robofleet.runtime.orchestrator import AgentOrchestrator

        workspace_cwd = AgentOrchestrator._resolve_workspace_cwd(config)

        env_vars = await self._spawn_env_vars(config, initial_prompt, workspace_cwd)
        template = self._build_task_template(env_vars, workspace_cwd)
        job = run_v2.Job(template=run_v2.ExecutionTemplate(template=template))
        await self._create_or_update_job(client, name, job)
        op = await asyncio.to_thread(
            client.run_job, request=run_v2.RunJobRequest(name=name)
        )
        execution_name = await _execution_name(op, client, name)
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
        field: an Execution carries ``Started`` / ``Completed`` /
        ``ContainerReady`` / ``ResourcesAvailable`` (verified live; ``Ready``
        exists on Jobs and Services, never on an Execution), and ``Completed``
        is ``CONDITION_SUCCEEDED`` on a clean finish and ``CONDITION_FAILED``
        on a non-zero task exit. A completed execution with no ``Completed``
        condition is treated as failed.
        """
        client = _executions_client()
        exe = await asyncio.to_thread(
            client.get_execution,
            request=run_v2.GetExecutionRequest(name=instance_id),
        )
        if exe.completion_time is None:
            return None  # still running
        for cond in exe.conditions:
            if getattr(cond, "type_", "") == "Completed":
                if cond.state == run_v2.Condition.State.CONDITION_SUCCEEDED:
                    return 0
                if cond.state == run_v2.Condition.State.CONDITION_FAILED:
                    return 1
        return 1  # completed but no Completed condition -> treat as failed

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
