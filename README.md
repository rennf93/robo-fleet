# robo-fleet

robo-fleet is a virtual AI company of 25 AI agents plus one human CEO that runs as a self-organizing software workforce on Google Cloud. Each agent is built on Google ADK and Gemini 3.5 Flash; together they plan, code, QA, review, and merge real tasks through a structured lifecycle, observable from a live control panel. This is the RoboFleet AI-agent-company system ported to the Google Cloud stack for the All Things Agentic hackathon, Fortified Enterprise Fleet track.

## Architecture overview

Three real changes from RoboFleet, everything else copied verbatim:

1. **Spawn backend: docker containers -> Cloud Run Jobs.** The orchestrator no longer `docker run`s an agent container per task. A `CloudRunJobsProvider` submits a Cloud Run Job execution (one image serves every role; role behavior comes from the tool manifest + composed system prompt) and polls the job to completion.
2. **Agent runtime: Claude Code CLI -> ADK Runner + Gemini 3.5 Flash.** The `robofleet-agent-adk` image runs `robofleet.agent.adk_entry`, which builds an ADK `LlmAgent` with the gateway tool-shim and git/file `FunctionTools`, runs it over an `InMemorySessionService` session on Gemini 3.5 Flash, accumulates token counts, and POSTs usage to `/api/v1/usage/report`. No MCP servers, no Claude CLI, no Node.js: a pure Python ADK runtime.
3. **Infra: homelab docker-compose -> Cloud SQL, Memorystore, Filestore, GCS, Secret Manager, Artifact Registry, Cloud Run.** Postgres + pgvector moves to Cloud SQL Postgres 16 (via the Cloud SQL python connector, `robofleet.infra.cloudsql`), Redis to Memorystore for Redis 7.x, the workspaces volume to a Filestore NFS share, agent clones to GCS, the Fernet key + HMAC secret + Gemini API key to Secret Manager, and the three images to Artifact Registry, built by Cloud Build.

Everything else (the org hierarchy, task lifecycle, gateway verbs, findings ledger, conventions standard, audit log, the Next.js panel) is unchanged from RoboFleet.

## Architecture diagram

See [`docs/architecture.png`](./docs/architecture.png) (rendered from `docs/architecture.mmd`; re-render with `npx -y @mermaid-js/mermaid-cli -i docs/architecture.mmd -o docs/architecture.png -t default -b white`).

## Prerequisites

- `gcloud` CLI authenticated to a GCP project (`gcloud auth login` and `gcloud auth application-default login`).
- `terraform` (the `infra/` directory is a terraform root module).
- The GCP project with billing enabled and the hackathon credit request approved.
- A Gemini API key (set as `ROBOFLEET_GEMINI_API_KEY` when seeding secrets).

## Spin-up

A judge with the prerequisites above and credits approved reaches a running stack by following these steps in order. Every script reads its GCP references from `ROBOFLEET_GCP_*` env vars and `terraform output`; no values are hardcoded.

```bash
# 1. Provision the infra (Cloud SQL, Memorystore, Filestore, GCS, Artifact
#    Registry, VPC connector, the Cloud Run service/job IAM). Review and apply:
cd infra
terraform init
terraform apply
cd ..

# 2. Seed the four Secret Manager secrets (Fernet key, agent-auth HMAC secret,
#    cloud-auth secret, Gemini API key). Requires ROBOFLEET_GEMINI_API_KEY.
ROBOFLEET_GEMINI_API_KEY=your-key ./infra/seed-secrets.sh PROJECT_ID

# 3. Build the three images (robofleet-orchestrator, robofleet-panel, robofleet-agent-adk)
#    into Artifact Registry via Cloud Build. Reads ROBOFLEET_GCP_PROJECT_ID and
#    ROBOFLEET_GCP_REGION; uses cloudbuild.yaml at the repo root.
export ROBOFLEET_GCP_PROJECT_ID=your-project
export ROBOFLEET_GCP_REGION=your-region
./infra/build-images.sh

# 4. Deploy the orchestrator to Cloud Run. Pulls Cloud SQL connection name,
#    Memorystore host, Filestore IP/share, and GCS bucket from terraform output,
#    substitutes the __PLACEHOLDER__ tokens in orchestrator-service.yaml, and
#    calls `gcloud run services replace`. Needs ROBOFLEET_DATABASE_PASSWORD,
#    ROBOFLEET_REDIS_PASSWORD, and the seeded cloud-auth CEO login.
export ROBOFLEET_DATABASE_PASSWORD=...
export ROBOFLEET_REDIS_PASSWORD=...
export ROBOFLEET_CLOUD_AUTH_EMAIL=ceo@example.com
export ROBOFLEET_CLOUD_AUTH_PASSWORD=...
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

A single judge-reproducible env template lives at `.env.gcp.example`; copy it to `.env.gcp` and fill the values from `terraform output` and Secret Manager. It documents every `ROBOFLEET_GCP_*` var, the DB/Redis connection details, the agent image registry/tag, and the feature flags armed (or deliberately off) for the GCP deploy.

## Env vars

See `.env.gcp.example` for the full set. One-line-per-section summary:

- **Database (Cloud SQL):** `ROBOFLEET_DATABASE_HOST` / `_PORT` / `_USER` / `_PASSWORD` / `_NAME` point at the Cloud SQL Auth Proxy sidecar.
- **Redis (Memorystore):** `ROBOFLEET_REDIS_HOST` / `_PORT` / `_PASSWORD` / `_DB` for the Memorystore instance.
- **GCP infra references:** `ROBOFLEET_GCP_PROJECT_ID`, `ROBOFLEET_GCP_REGION`, `ROBOFLEET_GCP_CLOUDSQL_INSTANCE`, `ROBOFLEET_GCP_MEMORYSTORE_HOST` / `_PORT`, `ROBOFLEET_GCP_FILESTORE_SHARE` / `_IP` / `_NFS_PATH`, `ROBOFLEET_GCP_VPC_CONNECTOR_NAME`, `ROBOFLEET_GCP_GCS_BUCKET`, `ROBOFLEET_GCP_ARTIFACT_REGISTRY_REPO`, `ROBOFLEET_GCP_CLOUD_RUN_AGENT_JOB_PREFIX`. The Filestore IP/path + VPC connector are attached to every agent Cloud Run Job as its NFS workspace volume; a developer Job refuses to spawn without them.
- **Vertex AI model location:** `ROBOFLEET_GCP_VERTEX_MODEL_LOCATION=global`, separate from the Cloud Run Job region. `gemini-3.5-flash` is served from the global Vertex endpoint (regional availability was preview-only through Aug 2026); empty falls back to `ROBOFLEET_GCP_REGION`.
- **Secrets (Secret Manager):** `ROBOFLEET_ENCRYPTION_KEY`, `ROBOFLEET_AGENT_AUTH_SECRET`, `ROBOFLEET_AGENT_AUTH_REQUIRED=true`, `ROBOFLEET_CLOUD_AUTH_SECRET`.
- **Cloud auth (armed on GCP):** `ROBOFLEET_CLOUD_AUTH_ENABLED=true`, `ROBOFLEET_CLOUD_AUTH_EMAIL` / `_PASSWORD` (the seeded CEO login).
- **URLs:** `ROBOFLEET_PUBLIC_BASE_URL` (the Cloud Run panel URL), `ROBOFLEET_API_URL` / `ROBOFLEET_ORCHESTRATOR_URL` (localhost in the orchestrator container; on the panel service `deploy-panel.sh` sets them to the orchestrator's public Cloud Run URL, and the panel's `proxy.ts` forwards `/api/*` there at request time).
- **Agent images:** `ROBOFLEET_AGENT_IMAGE_REGISTRY`, `ROBOFLEET_AGENT_IMAGE_TAG`.
- **Gemini:** `ROBOFLEET_AGENT_MODEL_DEFAULT` (the model the orchestrator injects into every agent Job as `ROBOFLEET_AGENT_MODEL`; defaults to `gemini-3.5-flash`), `ROBOFLEET_GEMINI_API_KEY` (Gemini API fallback; on Cloud Run the Jobs authenticate to Vertex AI with the compute service account).
- **Cost caps:** `ROBOFLEET_TASK_BUDGETS_ENABLED=true` arms `tasks.budget_usd` / `projects.monthly_budget_usd`; a breach blocks the task so a looping agent cannot burn credits.

## The 7 fleet properties

The Fortified Enterprise Fleet track scores seven fleet properties; all already exist in RoboFleet and map onto the Google stack:

1. **Agent registry** = the agent registry in `agents_config` / the `agents` DB table (25 agents + the human CEO), loaded at orchestrator startup.
2. **Runtime** = Cloud Run Jobs (one execution per agent task) running the ADK `Runner` + `LlmAgent` on Gemini 3.5 Flash in the `robofleet-agent-adk` image.
3. **Memory bank** = the pgvector knowledge base (in-house RAG engine) on Cloud SQL plus the organizational-memory loop (learnings + playbooks, captured on task completion and injected into the next claim's briefing).
4. **Identity** = per-agent HMAC tokens (`X-Agent-Token`, signed with `ROBOFLEET_AGENT_AUTH_SECRET`) for the agent gateway, plus FastAPI Users cloud auth (cookie + JWT) for the human CEO on the public panel.
5. **Gateway** = the Choreographer + the `robofleet-flow` / `robofleet-do` v1 routes (`/api/v1/flow/{role}/{verb}` and `/api/v1/do`); agents never call domain services directly, only through intent verbs that return a standardized Envelope.
6. **Model armor** = the task-content guardrails (prompt-injection guard, forbidden-content screening, per-role tool manifests) + the architectural-conventions standard, enforced at `i_am_done` and the in-path PR-review gate.
7. **Observability** = the `audit_log` transition journal + `MetricsService` (cycle time, rework, spawn-waste) surfaced in the panel, plus Cloud Logging for the Cloud Run services and jobs.

## Reproducibility

This repository is licensed under AGPL-3.0 (see [`LICENSE`](./LICENSE)). A judge following the spin-up above, with a GCP project and the credit request approved, reaches a running stack. The live deploy (Cloud SQL, Memorystore, Cloud Run) costs GCP credits; the repo itself, the compliance test (`tests/compliance/test_hackathon_stack.py`), and the unit-test suite run anywhere with `uv sync` and a local Postgres.

## Testing

Two tiers, both judge-reproducible without a GCP project or credits.

**Tier 1: the compliance proof (no infra).** The compliance test is the proof-the-stack-is-Google artifact (`tests/compliance/test_hackathon_stack.py`). It asserts the three mandatory All Things Agentic items and fails (not skips) if the dependency is missing: the agent model resolves to a `gemini-3.5-*` id, Google ADK's `Runner` is importable, and the Cloud SQL engine factory is wired. No database and no GCP project required:

```bash
uv sync
uv run pytest tests/compliance/test_hackathon_stack.py -v
```

A live-GCP assertion in the same file skips unless `ROBOFLEET_GCP_E2E=1` is set, so it probes the deployed stack only when you point it at one.

**Tier 2: the full suite (local Postgres).** The unit and integration suite covers the task lifecycle, the gateway verbs, the findings ledger, the sequencing bar, the conventions standard, and the GCP infra adapters (Cloud SQL, Memorystore, GCS, Secret Manager, Filestore). The DB-backed tests need a Postgres; `docker compose up -d postgres` brings up `pgvector/pgvector:pg16` on `localhost:15432` with user/password/database `robofleet`, which matches the test conftest defaults so no env vars are needed. The conftest provisions an ephemeral test database, enables pgvector, and builds the schema itself, so there is no `alembic upgrade` step:

```bash
uv sync
docker compose up -d postgres      # pgvector Postgres on localhost:15432 (matches test defaults)
uv run pytest                      # full suite
make quality                       # the full gate: ruff + format + markdown + mypy + pytest + xenon
```

The GCP infra-adapter tests stub the real GCP calls (no project, no credits needed); only the live-GCP compliance assertion needs `ROBOFLEET_GCP_E2E=1` and a deployed stack.

## Development

```bash
uv sync                       # install deps (google-adk is a main dep)
docker compose up -d postgres redis ollama   # backing services only (local dev)
uv run alembic upgrade head   # migrate the database
uv run python -m robofleet.cli   # API + orchestrator
uv run pytest                 # tests
make quality                  # the full gate (ruff/format/markdown/mypy/pytest/xenon)
```

## License

Copyright (c) 2026 Renzo Franceschini. Licensed under AGPL-3.0; see [`LICENSE`](./LICENSE) for the full text. The AGPL's network-use clause (section 13) means that if you run a modified version of robo-fleet as a network service, you must make your modified source available to its users.
