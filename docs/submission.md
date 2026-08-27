# robo-fleet - All Things Agentic submission

## Category

Fortified Enterprise Fleet

## Hosted URL

- Control panel (the demo surface, CEO login via cloud auth): https://robofleet-panel-813757481440.us-central1.run.app
- Orchestrator API (public probes: `/health`, `/api/auth/status`): https://robofleet-orchestrator-813757481440.us-central1.run.app

Both are Cloud Run services in `robofleet-deploy` (`us-central1`). Behind them: Cloud SQL Postgres 16 + pgvector, Memorystore for Redis, Filestore (agent git workspaces over NFS), GCS (run diagnostics, renders), Secret Manager (the Fernet key, the agent-auth HMAC secret, the cloud-auth secret, and one rotated secret per agent credential), Artifact Registry (three images built by Cloud Build), and a Serverless VPC Access connector. Each agent turn is a Cloud Run Job execution of the `robofleet-agent-adk` image running the ADK Runner on `gemini-3.5-flash` through Vertex AI's global endpoint.

## Repo

Public: https://github.com/rennf93/robo-fleet (AGPL-3.0). The GCP port lives on `feature/gcp-port` (PR #1 into `master`). No sharing step is needed for a public repo; the judge emails (`testing@devpost.com`, `cloudhackathons@google.com`) are listed in the Devpost form as a courtesy.

## Live evidence

The full delivery lifecycle ran agent-driven on the hosted stack on 2026-08-26: task `b154f3be` went pending -> claimed -> in_progress -> awaiting_qa -> needs_revision (three QA bounces with structured, file-and-line findings) -> awaiting_qa -> awaiting_documentation -> awaiting_pm_review -> awaiting_ceo_approval -> completed, with PR #3 squash-merged to `master` by the CEO from the API. Every leg (developer, QA, documenter, PM, auditor) ran as a Cloud Run Job on `gemini-3.5-flash`; the whole cycle cost $0.61 in Gemini usage, metered per agent through the usage ledger and capped by the task/project budgets. `GET /api/tasks/{id}/governance` on that task returns the reconstructed gate chain (conventions -> self-verification -> QA -> PR gate -> PM review -> CEO approval), all passed.

## Demo video

TBD: `<YouTube link after recording>`

A public post of the demo video earns the social-post bonus (+0.2). The link above is replaced once the video is recorded and uploaded as unlisted, then made public for the bonus.

## Text description

robo-fleet is a virtual AI company of 25 AI agents plus one human CEO that runs as a self-organizing software workforce on Google Cloud. Each agent is built on Google ADK and Gemini 3.5 Flash; together they plan, code, QA, review, and merge real software tasks through a structured lifecycle (backlog -> pending -> claimed -> in_progress -> verifying -> awaiting_qa -> awaiting_documentation -> awaiting_pm_review -> awaiting_ceo_approval -> completed), observable from a live Next.js control panel.

The fleet architecture maps the seven fleet properties onto the Google stack: a 25-agent registry in the DB, a Cloud Run Job runtime per agent turn running the ADK Runner on Gemini 3.5 Flash via Vertex AI (each Job mounts its per-task git worktree from Filestore over NFS and gets its credentials as Secret Manager `secretKeyRef`s, never plain env), a pgvector memory bank on Cloud SQL plus an organizational-memory loop, per-agent HMAC-token identity plus FastAPI Users cloud auth for the CEO, a Choreographer gateway exposing flow/do intent-verb routes that return a standardized Envelope, task-content guardrails + injection guard + a per-task `intends_to_touch` scope check at the PR gate as model armor, and an audit_log + per-verb latency samples + metrics (cycle time, rework, spawn waste, a per-task governance report) observability layer. Cost is a first-class control: every Job's token usage lands in a per-agent ledger and the task/project budget caps block a runaway task before it can burn credits. The Google infra used: Cloud Run (services + Jobs), Vertex AI, Cloud SQL Postgres 16, Memorystore for Redis, Filestore, GCS, Secret Manager, Artifact Registry, Cloud Build, Serverless VPC Access.

## Bonus claims

- **Social post (+0.2):** TBD - a public X/LinkedIn post linking the demo video. Filed once the video is public.
- **Blog (+0.2):** TBD - a public blog post (Medium or the project docs site) walking through the fleet architecture and the Google-stack port. Filed before the deadline.
- **Veo (+0.2):** stretch, pending CEO decision on the video engine. The RoboFleet video engine (HyperFrames craft program + motion design bar) can be wired to the Veo API as the generator backend, but the CEO has not yet confirmed keeping the video engine in the robo-fleet scope. If confirmed, the wiring is a generator-side swap (video engine -> Veo API) and a demo clip; if not, this bonus is dropped.

## Compliance proof

The repo ships a compliance test at `tests/compliance/test_hackathon_stack.py` that asserts the three mandatory stack items and fails (not skips) if ADK or the Gemini 3.5 model is missing:

1. `google.adk.runners.Runner` is importable (ADK is the agent framework).
2. `robofleet.agent.adk_entry._MODEL` resolves to a `gemini-3.5-*` id (Gemini 3.5+ via Gemini API/Vertex).
3. `robofleet.infra.cloudsql.async_engine_for_cloudsql` is callable and `get_engine` routes through it when `gcp_cloudsql_instance` is armed (>=1 Google Cloud infra service wired).

Run it with `uv run pytest tests/compliance/ -v`. The live-GCP assertion (`test_live_gcp_cloudsql_instance_configured`) skips unless `ROBOFLEET_GCP_E2E=1` is set against the deployed stack.