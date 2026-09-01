# robo-fleet

robo-fleet is a virtual AI company of 26 AI agents plus one human CEO that runs as a self-organizing software workforce on Google Cloud. Each agent is built on Google ADK and Gemini 3.5 Flash; together they plan, code, QA, review, and merge real tasks through a structured lifecycle, observable from a live control panel. This is the RoboFleet AI-agent-company system ported to the Google Cloud stack for the All Things Agentic hackathon, Fortified Enterprise Fleet track.

The 26 agents: 3 delivery cells (backend, frontend, UX/UI) of 6 agents each (2 developers, 1 QA, 1 PM, 1 documenter, 1 PR reviewer) = 18, a Main PM coordinating the cells, a 3-member Board (Product Owner, Head of Marketing, Auditor), 2 global/overflow PR reviewers, and an Intake interviewer + a Secretary that only chat with the human CEO. See [`docs/architecture.md`](./docs/architecture.md) for the full breakdown and [`docs/agents.md`](./docs/agents.md) for per-role detail.

## Architecture overview

Three real changes from RoboFleet, everything else copied verbatim:

1. **Spawn backend: docker containers -> Cloud Run Jobs.** The orchestrator no longer `docker run`s a delivery agent container per task. A `CloudRunJobsProvider` (`robofleet/llm/providers/cloudrun_jobs.py`) creates (or updates) a per-agent Cloud Run Job, starts an execution, and the orchestrator's health loop polls it to completion (one image serves every role; role behavior comes from the tool manifest + composed system prompt).
2. **Agent runtime: Claude Code CLI -> ADK Runner + Gemini 3.5 Flash.** The `robofleet-agent-adk` image runs `robofleet.agent.adk_entry`, which builds an ADK `LlmAgent` with the gateway tool-shim (plain HTTP, no MCP) and git/file `FunctionTools`, runs it over an `InMemorySessionService` session on Gemini 3.5 Flash, accumulates token counts, and POSTs usage to `/api/v1/usage/report`. No MCP servers, no Claude CLI, no Node.js in that image: a pure Python ADK runtime.
3. **Infra: homelab docker-compose -> Cloud SQL, Memorystore, Filestore, GCS, Secret Manager, Artifact Registry, Cloud Run.** Postgres + pgvector moves to Cloud SQL Postgres 16 (via the Cloud SQL python connector, `robofleet.infra.cloudsql`), Redis to Memorystore for Redis 7.x, the shared workspaces volume (per-agent git clones/worktrees) to a Filestore NFS share mounted at `/data/workspaces` on the orchestrator *and* every agent Job, the Fernet key + agent-auth HMAC secret + cloud-auth secret + Gemini API key + DB password + CEO login password (six secrets) to Secret Manager, and the three images to Artifact Registry, built by Cloud Build. GCS holds the per-spawn ADK tool-manifest JSON and best-effort crash/heartbeat diagnostics, not the git clones.

Everything else (the org hierarchy, task lifecycle, gateway verbs, findings ledger, conventions standard, audit log, the Next.js panel) is unchanged from RoboFleet.

**What's inherited but not part of this deploy.** The repo still carries the predecessor's full surface area, most of it dormant or dead-routed on GCP, not deleted:

- Four other model-provider spawn backends (Grok, Codex/OpenAI, a Gemini-CLI provider distinct from the ADK runtime, Kimi) are still registered in `AgentOrchestrator`'s provider registry, but startup unconditionally seeds GLOBAL routing at `ADK_CLOUD_RUN` whenever `ROBOFLEET_GCP_PROJECT_ID` is set (`robofleet/services/llm.py:seed_adk_cloud_run_routing`), so they never get dispatched to in this deploy. The predecessor's Claude Code CLI docker spawn path was removed outright.
- The MCP servers under `robofleet/mcp/` still exist and back the **interactive** Intake and Secretary chat agents (human-facing task drafting / chief-of-staff), which spawn as long-lived local `docker run` containers (`AgentOrchestrator._run_container_cmd`), unchanged from the predecessor. The Cloud Run orchestrator container has no Docker daemon, so those two chat roles do not run on the actual Cloud Run deployment; every delivery-lifecycle agent (developer/QA/PM/documenter/reviewer/board) is unaffected, since those spawn through `CloudRunJobsProvider`, not `docker run`.
- The Telegram notifications bridge, the video-render engine (Remotion/HyperFrames + a separate `video-renderer` Node service), and the X/Twitter posting engine are present in code and behind their own feature flags, all left off in `.env.gcp.example` for this deploy.

## Architecture diagram

See [`docs/architecture.png`](./docs/architecture.png). The source is [`docs/architecture.svg`](./docs/architecture.svg); re-render the PNG with any headless Chromium, e.g. `chrome --headless --force-device-scale-factor=2 --window-size=1680,1000 --screenshot=docs/architecture.png file://$PWD/docs/architecture.svg`.

## Where to look first

- [`docs/architecture.md`](./docs/architecture.md) — the deeper technical picture: the end-to-end spawn/request flow, what lives in each data store, and the panel/orchestrator split.
- The panel itself, once deployed (step 6 below): the **Kanban** and **Tasks** pages show the task lifecycle live, **Agents** shows the 26-agent roster and their current state, **Git** shows PRs/branches, and **Metrics** shows cycle time / rework / spawn-waste and the per-task governance report.
- `docs/deploy.md`, `docs/operations.md`, and `docs/configuration.md` cover deploying, running, and configuring the stack in more depth than the Spin-up section below.
- [`docs/lifecycle.md`](./docs/lifecycle.md), [`docs/agents.md`](./docs/agents.md), and [`docs/gateway.md`](./docs/gateway.md) cover the task state machine, the per-role agent breakdown, and the flow/do gateway verb surface.
- [`docs/rag/`](./docs/rag/README.md) is the agent-facing knowledge corpus the agents themselves query; it is not written for a human reader but is a source of truth for exactly what each role is told to do.

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

# 2. Seed the six Secret Manager secrets (Fernet key, agent-auth HMAC secret,
#    cloud-auth secret, Gemini API key, Cloud SQL password, and a generated CEO
#    login password). Requires ROBOFLEET_GEMINI_API_KEY and ROBOFLEET_DATABASE_PASSWORD.
ROBOFLEET_GEMINI_API_KEY=your-key ROBOFLEET_DATABASE_PASSWORD=... ./infra/seed-secrets.sh PROJECT_ID
# Read the generated CEO password back when you need to log in:
gcloud secrets versions access latest --secret=robofleet-cloud-auth-password

# 3. Build the three images (robofleet-orchestrator, robofleet-panel, robofleet-agent-adk)
#    into Artifact Registry via Cloud Build. Reads ROBOFLEET_GCP_PROJECT_ID and
#    ROBOFLEET_GCP_REGION; uses cloudbuild.yaml at the repo root. The panel bakes
#    the orchestrator's public URL into its rewrites at build time, so
#    ROBOFLEET_API_URL must be set (the orchestrator's Cloud Run URL).
export ROBOFLEET_GCP_PROJECT_ID=your-project
export ROBOFLEET_GCP_REGION=your-region
export ROBOFLEET_API_URL=https://robofleet-orchestrator-XXXX.your-region.run.app
./infra/build-images.sh

# 4. Deploy the orchestrator to Cloud Run. Pulls Cloud SQL connection name,
#    Memorystore host, Filestore IP/share, and GCS bucket from terraform output,
#    substitutes the __PLACEHOLDER__ tokens in orchestrator-service.yaml, and
#    calls `gcloud run services replace`. Passwords come from Secret Manager
#    (step 2); only the CEO login email is a deploy input.
export ROBOFLEET_REDIS_PASSWORD=...
export ROBOFLEET_CLOUD_AUTH_EMAIL=ceo@example.com
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
- **URLs:** `ROBOFLEET_PUBLIC_BASE_URL` (the Cloud Run panel URL), `ROBOFLEET_API_URL` / `ROBOFLEET_ORCHESTRATOR_URL` (the orchestrator's own public Cloud Run URL on the orchestrator service, used both for its self-calls and as the callback URL every spawned agent Job gets; `deploy-panel.sh` sets the same value on the panel service, whose `next.config.ts` bakes it into build-time rewrites that forward `/api/*`, `/ws/*`, and `/health` there. `proxy.ts`, Next 16's middleware, reads the same variable at **request** time and rewrites `/api/*` and `/health` to the orchestrator itself, which is what makes the Cloud Run panel work when the build-time value was wrong or absent; it also probes `/api/auth/status` to gate the dashboard behind login. WebSocket upgrades ride the build-time rewrite only).
- **Agent images:** `ROBOFLEET_AGENT_IMAGE_REGISTRY`, `ROBOFLEET_AGENT_IMAGE_TAG`.
- **Gemini:** `ROBOFLEET_AGENT_MODEL_DEFAULT` (the model the orchestrator injects into every agent Job as `ROBOFLEET_AGENT_MODEL`; defaults to `gemini-3.5-flash`), `ROBOFLEET_GEMINI_API_KEY` (Gemini API fallback; on Cloud Run the Jobs authenticate to Vertex AI with the compute service account).
- **Cost caps:** `ROBOFLEET_TASK_BUDGETS_ENABLED=true` arms `tasks.budget_usd` / `projects.monthly_budget_usd`; a breach blocks the task so a looping agent cannot burn credits.

## The 7 fleet properties

The Fortified Enterprise Fleet track scores seven fleet properties; all already exist in RoboFleet and map onto the Google stack:

1. **Agent registry** = the single source-of-truth registry in `robofleet/foundation/identity.py` (`AGENTS`, 26 real agent slugs + the human CEO + a `system` sentinel), mirrored into the `agents` DB table at startup.
2. **Runtime** = Cloud Run Jobs (one execution per agent turn) running the ADK `Runner` + `LlmAgent` on Gemini 3.5 Flash in the `robofleet-agent-adk` image, authenticated to Vertex AI via the Job's own runtime service account (no API key on the primary GCP path).
3. **Memory bank** = the pgvector knowledge base (in-house RAG engine) on Cloud SQL plus the organizational-memory loop (learnings + playbooks, captured on task completion and injected into the next claim's briefing).
4. **Identity** = per-agent HMAC tokens (`X-Agent-Token`, signed with `ROBOFLEET_AGENT_AUTH_SECRET`, stored per-spawn as a rotated Secret Manager secret rather than a plain Job env value) for the agent gateway, plus FastAPI Users cloud auth (cookie + JWT) for the human CEO on the public panel.
5. **Gateway** = the Choreographer + the `/api/v1/flow/{role}/{verb}` and `/api/v1/do/{tool}` v1 routes; agents never call domain services directly, only through intent verbs that return a standardized Envelope.
6. **Model armor** = the task-content guardrails (prompt-injection guard in `robofleet/foundation/policy/injection_guard.py`, forbidden-content screening, per-role tool manifests) + the architectural-conventions standard, enforced at `i_am_done` and the in-path PR-review gate.
7. **Observability** = the `audit_log` transition journal + `MetricsService` (cycle time, rework, spawn-waste) + a per-task governance report (`GET /api/tasks/{id}/governance`) surfaced in the panel, plus Cloud Logging for the Cloud Run services and jobs.

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
