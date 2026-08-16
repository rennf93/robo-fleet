"""Cloud Run Jobs spawn backend for ADK+Gemini agents.

On GCP there is no Docker daemon, so the orchestrator cannot shell out to
``docker run``. Instead each agent runs as a Cloud Run Job execution: this
provider creates (or updates) the Job, then ``run_job`` starts an execution
and returns its fully-qualified name as the instance handle. The docker path
stays intact for local dev; this provider is only resolved for agents whose
``ModelProvider`` is ``ADK_CLOUD_RUN``.

The orchestrator writes the tool manifest (flow/do tools + system prompt) to a
local file and hands its ``Path`` here; this provider uploads it to GCS and
points the job at the ``gs://`` URI via ``ROBOCO_TOOL_MANIFEST_PATH``, so the
orchestrator itself never touches GCS.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from google.cloud import run_v2

from roboco.config import settings
from roboco.llm.providers.base import AgentProvider, ProviderError, SpawnResult

if TYPE_CHECKING:
    from pathlib import Path

    from roboco.models.runtime import OrchestratorAgentConfig as AgentConfig

# Model id ADK agents run on Cloud Run. The orchestrator does not pin a CLI
# here (no shell-out); this is the Gemini model id the agent container's ADK
# runtime is configured against.
_GEMINI_MODEL = "gemini-3.5-flash"

# Job max runtime. Cloud Run Jobs caps an execution at this wall-clock.
_JOB_TIMEOUT_SECONDS = 1800


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
        name = _job_name(config.agent_id)
        client = _jobs_client()
        env_vars = [
            run_v2.EnvVar(name="ROBOCO_INITIAL_PROMPT", value=initial_prompt or ""),
            run_v2.EnvVar(name="ROBOCO_AGENT_ID", value=config.agent_id),
            run_v2.EnvVar(name="ROBOCO_AGENT_MODEL", value=_GEMINI_MODEL),
        ]
        # The orchestrator writes the ADK tool manifest to config.mcp_config_path
        # (via _generate_adk_manifest); upload THAT to GCS, not the Claude-Code
        # settings.json (agent_settings_path, irrelevant for ADK). The entrypoint
        # fetches it via ROBOCO_TOOL_MANIFEST_PATH.
        manifest_uri = await _upload_manifest(config.mcp_config_path, config.agent_id)
        if manifest_uri:
            env_vars.append(
                run_v2.EnvVar(name="ROBOCO_TOOL_MANIFEST_PATH", value=manifest_uri)
            )
        template = run_v2.TaskTemplate(
            containers=[run_v2.Container(image=self._image, env=env_vars)],
            timeout={"seconds": _JOB_TIMEOUT_SECONDS},
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
