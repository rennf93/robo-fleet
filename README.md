# robo-fleet

robo-fleet is a virtual AI company of 25 AI agents plus one human CEO that runs as a self-organizing software workforce on Google Cloud. Each agent is built on Google ADK and Gemini 3.5 Flash; together they plan, code, QA, review, and merge real tasks through a structured lifecycle, observable from a live control panel. This is the RoboCo AI-agent-company system ported to the Google Cloud stack for the All Things Agentic hackathon, Fortified Enterprise Fleet track.

## Architecture overview

Three real changes from RoboCo, everything else copied verbatim:

1. **Spawn backend: docker containers -> Cloud Run Jobs.** The orchestrator no longer `docker run`s an agent container per task. A `CloudRunJobsProvider` submits a Cloud Run Job execution (one image serves every role; role behavior comes from the tool manifest + composed system prompt) and polls the job to completion.
2. **Agent runtime: Claude Code CLI -> ADK Runner + Gemini 3.5 Flash.** The `roboco-agent-adk` image runs `roboco.agent.adk_entry`, which builds an ADK `LlmAgent` with the gateway tool-shim and git/file `FunctionTools`, runs it over an `InMemorySessionService` session on Gemini 3.5 Flash, accumulates token counts, and POSTs usage to `/api/v1/usage/report`. No MCP servers, no Claude CLI, no Node.js: a pure Python ADK runtime.
3. **Infra: homelab docker-compose -> Cloud SQL, Memorystore, Filestore, GCS, Secret Manager, Artifact Registry, Cloud Run.** Postgres + pgvector moves to Cloud SQL Postgres 16 (via the Cloud SQL python connector, `roboco.infra.cloudsql`), Redis to Memorystore for Redis 7.x, the workspaces volume to a Filestore NFS share, agent clones to GCS, the Fernet key + HMAC secret + Gemini API key to Secret Manager, and the three images to Artifact Registry, built by Cloud Build.

Everything else (the org hierarchy, task lifecycle, gateway verbs, findings ledger, conventions standard, audit log, the Next.js panel) is unchanged from RoboCo.

## Architecture diagram

See `docs/architecture.mmd` (render to `docs/architecture.png` with `npx -y @mermaid-js/mermaid-cli -i docs/architecture.mmd -o docs/architecture.png` if a local mermaid CLI is available).

## Prerequisites

- `gcloud` CLI authenticated to a GCP project (`gcloud auth login` and `gcloud auth application-default login`).
- `terraform` (the `infra/` directory is a terraform root module).
- The GCP project with billing enabled and the hackathon credit request approved.
- A Gemini API key (set as `ROBOCO_GEMINI_API_KEY` when seeding secrets).

## Spin-up

A judge with the prerequisites above and credits approved reaches a running stack by following these steps in order. Every script reads its GCP references from `ROBOCO_GCP_*` env vars and `terraform output`; no values are hardcoded.

```bash
# 1. Provision the infra (Cloud SQL, Memorystore, Filestore, GCS, Artifact
#    Registry, VPC connector, the Cloud Run service/job IAM). Review and apply:
cd infra
terraform init
terraform apply
cd ..

# 2. Seed the four Secret Manager secrets (Fernet key, agent-auth HMAC secret,
#    cloud-auth secret, Gemini API key). Requires ROBOCO_GEMINI_API_KEY.
ROBOCO_GEMINI_API_KEY=your-key ./infra/seed-secrets.sh PROJECT_ID

# 3. Build the three images (roboco-orchestrator, roboco-panel, roboco-agent-adk)
#    into Artifact Registry via Cloud Build. Reads ROBOCO_GCP_PROJECT_ID and
#    ROBOCO_GCP_REGION; uses cloudbuild.yaml at the repo root.
export ROBOCO_GCP_PROJECT_ID=your-project
export ROBOCO_GCP_REGION=your-region
./infra/build-images.sh

# 4. Deploy the orchestrator to Cloud Run. Pulls Cloud SQL connection name,
#    Memorystore host, Filestore IP/share, and GCS bucket from terraform output,
#    substitutes the __PLACEHOLDER__ tokens in orchestrator-service.yaml, and
#    calls `gcloud run services replace`. Needs ROBOCO_DATABASE_PASSWORD,
#    ROBOCO_REDIS_PASSWORD, and the seeded cloud-auth CEO login.
export ROBOCO_DATABASE_PASSWORD=...
export ROBOCO_REDIS_PASSWORD=...
export ROBOCO_CLOUD_AUTH_EMAIL=ceo@example.com
export ROBOCO_CLOUD_AUTH_PASSWORD=...
./infra/deploy-orchestrator.sh

# 5. Deploy the panel to Cloud Run. Discovers the orchestrator's Cloud Run URL
#    from the deployed service, substitutes panel-service.yaml, and calls
#    `gcloud run services replace`.
./infra/deploy-panel.sh

# 6. Open the panel URL printed by step 5, log in with the cloud-auth CEO
#    credentials, and drive a task from the Board -> Main PM -> cells -> dev
#    pipeline. The orchestrator spawns each agent as a Cloud Run Job running
#    ADK on Gemini 3.5 Flash.
```

A single judge-reproducible env template lives at `.env.gcp.example`; copy it to `.env.gcp` and fill the values from `terraform output` and Secret Manager. It documents every `ROBOCO_GCP_*` var, the DB/Redis connection details, the agent image registry/tag, and the feature flags armed (or deliberately off) for the GCP deploy.

## Env vars

See `.env.gcp.example` for the full set. One-line-per-section summary:

- **Database (Cloud SQL):** `ROBOCO_DATABASE_HOST` / `_PORT` / `_USER` / `_PASSWORD` / `_NAME` point at the Cloud SQL Auth Proxy sidecar.
- **Redis (Memorystore):** `ROBOCO_REDIS_HOST` / `_PORT` / `_PASSWORD` / `_DB` for the Memorystore instance.
- **GCP infra references:** `ROBOCO_GCP_PROJECT_ID`, `ROBOCO_GCP_REGION`, `ROBOCO_GCP_CLOUDSQL_INSTANCE`, `ROBOCO_GCP_MEMORYSTORE_HOST` / `_PORT`, `ROBOCO_GCP_FILESTORE_SHARE`, `ROBOCO_GCP_GCS_BUCKET`, `ROBOCO_GCP_ARTIFACT_REGISTRY_REPO`, `ROBOCO_GCP_CLOUD_RUN_AGENT_JOB_PREFIX`.
- **Secrets (Secret Manager):** `ROBOCO_ENCRYPTION_KEY`, `ROBOCO_AGENT_AUTH_SECRET`, `ROBOCO_AGENT_AUTH_REQUIRED=true`, `ROBOCO_CLOUD_AUTH_SECRET`.
- **Cloud auth (armed on GCP):** `ROBOCO_CLOUD_AUTH_ENABLED=true`, `ROBOCO_CLOUD_AUTH_EMAIL` / `_PASSWORD` (the seeded CEO login).
- **URLs:** `ROBOCO_PUBLIC_BASE_URL` (the Cloud Run panel URL), `ROBOCO_API_URL` / `ROBOCO_ORCHESTRATOR_URL` (localhost in the orchestrator container).
- **Agent images:** `ROBOCO_AGENT_IMAGE_REGISTRY`, `ROBOCO_AGENT_IMAGE_TAG`.
- **Gemini:** `ROBOCO_GEMINI_API_KEY`, `ROBOCO_AGENT_MODEL` (defaults to `gemini-3.5-flash` in `roboco.agent.adk_entry`).

## The 7 fleet properties

The Fortified Enterprise Fleet track scores seven fleet properties; all already exist in RoboCo and map onto the Google stack:

1. **Agent registry** = the agent registry in `agents_config` / the `agents` DB table (25 agents + the human CEO), loaded at orchestrator startup.
2. **Runtime** = Cloud Run Jobs (one execution per agent task) running the ADK `Runner` + `LlmAgent` on Gemini 3.5 Flash in the `roboco-agent-adk` image.
3. **Memory bank** = the pgvector knowledge base (in-house RAG engine) on Cloud SQL plus the organizational-memory loop (learnings + playbooks, captured on task completion and injected into the next claim's briefing).
4. **Identity** = per-agent HMAC tokens (`X-Agent-Token`, signed with `ROBOCO_AGENT_AUTH_SECRET`) for the agent gateway, plus FastAPI Users cloud auth (cookie + JWT) for the human CEO on the public panel.
5. **Gateway** = the Choreographer + the `roboco-flow` / `roboco-do` v1 routes (`/api/v1/flow/{role}/{verb}` and `/api/v1/do`); agents never call domain services directly, only through intent verbs that return a standardized Envelope.
6. **Model armor** = the task-content guardrails (prompt-injection guard, forbidden-content screening, per-role tool manifests) + the architectural-conventions standard, enforced at `i_am_done` and the in-path PR-review gate.
7. **Observability** = the `audit_log` transition journal + `MetricsService` (cycle time, rework, spawn-waste) surfaced in the panel, plus Cloud Logging for the Cloud Run services and jobs.

## Reproducibility

This repository is licensed under AGPL-3.0 (see [`LICENSE`](./LICENSE)). A judge following the spin-up above, with a GCP project and the credit request approved, reaches a running stack. The live deploy (Cloud SQL, Memorystore, Cloud Run) costs GCP credits; the repo itself, the compliance test (`tests/compliance/test_hackathon_stack.py`), and the unit-test suite run anywhere with `uv sync` and a local Postgres.

## Development

```bash
uv sync                       # install deps (google-adk is a main dep)
docker compose up -d postgres redis ollama   # backing services only (local dev)
uv run alembic upgrade head   # migrate the database
uv run python -m roboco.cli   # API + orchestrator
uv run pytest                 # tests
make quality                  # the full gate (ruff/format/markdown/mypy/pytest/xenon)
```

## License

Copyright (c) 2026 Renzo Franceschini. Licensed under AGPL-3.0; see [`LICENSE`](./LICENSE) for the full text. The AGPL's network-use clause (section 13) means that if you run a modified version of robo-fleet as a network service, you must make your modified source available to its users.