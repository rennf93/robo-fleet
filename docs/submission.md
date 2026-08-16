# robo-fleet - All Things Agentic submission

## Category

Fortified Enterprise Fleet

## Hosted URL

TBD: `<run.app URL after deploy>`

The live stack deploys to Cloud Run (panel + orchestrator) with Cloud SQL, Memorystore, Filestore, GCS, Secret Manager, and Artifact Registry behind it. The deploy is gated on the GCP credit request being approved; the URL placeholder above is replaced once Task 6.1 (live GCP e2e) lands.

## Repo sharing

Share the private repo with the judges at:

- `testing@devpost.com`
- `cloudhackathons@google.com`

Steps:

1. Push `feature/gcp-port` to the repo (or open a PR to the default branch and share that).
2. In the GitHub repo, Settings -> Collaborators and teams -> Add people.
3. Paste `testing@devpost.com` and `cloudhackathons@google.com`, grant Read access.
4. Repeat for the GitHub repo's Settings -> General -> Danger Zone -> "Allow access to private fork issues" if the judges need to file issues.

## Demo video

TBD: `<unlisted YouTube link after Task 6.2 record>`

A public post of the demo video earns the social-post bonus (+0.2). The link above is replaced once the video is recorded and uploaded as unlisted, then made public for the bonus.

## Text description

robo-fleet is a virtual AI company of 25 AI agents plus one human CEO that runs as a self-organizing software workforce on Google Cloud. Each agent is built on Google ADK and Gemini 3.5 Flash; together they plan, code, QA, review, and merge real software tasks through a structured lifecycle (backlog -> pending -> claimed -> in_progress -> verifying -> awaiting_qa -> awaiting_documentation -> awaiting_pm_review -> awaiting_ceo_approval -> completed), observable from a live Next.js control panel.

The fleet architecture maps the seven fleet properties onto the Google stack: a 25-agent registry in the DB, a Cloud Run Job runtime per agent task running the ADK Runner on Gemini 3.5 Flash, a pgvector memory bank on Cloud SQL plus an organizational-memory loop, per-agent HMAC-token identity plus FastAPI Users cloud auth for the CEO, a Choreographer gateway exposing flow/do intent-verb routes, task-content guardrails + injection guard as model armor, and an audit_log + metrics + Cloud Logging observability layer. The Google infra used: Cloud Run, Cloud SQL Postgres 16, Memorystore for Redis, Filestore, GCS, Secret Manager, Artifact Registry, Cloud Build.

## Bonus claims

- **Social post (+0.2):** TBD - a public X/LinkedIn post linking the demo video. Filed once the video is public.
- **Blog (+0.2):** TBD - a public blog post (Medium or the project docs site) walking through the fleet architecture and the Google-stack port. Filed before the deadline.
- **Veo (+0.2):** stretch, pending CEO decision on the video engine. The RoboCo video engine (HyperFrames craft program + motion design bar) can be wired to the Veo API as the generator backend, but the CEO has not yet confirmed keeping the video engine in the robo-fleet scope. If confirmed, the wiring is a generator-side swap (video engine -> Veo API) and a demo clip; if not, this bonus is dropped.

## Compliance proof

The repo ships a compliance test at `tests/compliance/test_hackathon_stack.py` that asserts the three mandatory stack items and fails (not skips) if ADK or the Gemini 3.5 model is missing:

1. `google.adk.runners.Runner` is importable (ADK is the agent framework).
2. `roboco.agent.adk_entry._MODEL` resolves to a `gemini-3.5-*` id (Gemini 3.5+ via Gemini API/Vertex).
3. `roboco.infra.cloudsql.async_engine_for_cloudsql` is callable and `get_engine` routes through it when `gcp_cloudsql_instance` is armed (>=1 Google Cloud infra service wired).

Run it with `uv run pytest tests/compliance/ -v`. The live-GCP assertion (`test_live_gcp_cloudsql_instance_configured`) skips unless `ROBOFLEET_GCP_E2E=1` is set against the deployed stack.