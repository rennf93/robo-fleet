# Deploying to GCP (zero to running stack)

This is the path the hackathon deploy actually took: Terraform provisions the data plane, Cloud Build builds three images, two `gcloud run services replace` calls stand up the orchestrator and panel, and agents run as Cloud Run Job executions of a single ADK+Gemini image. Every command below is either copied from a script/Makefile in this repo or is a standard `gcloud`/`terraform`/`alembic` invocation whose arguments come from those files. Steps that pull a value from `terraform output` are called out explicitly — don't hand-type a resource id you can read back from state.

For the local/self-hosted alternative (`docker-compose.yml`, no GCP account needed), see `make quickstart` / `scripts/bootstrap.sh` instead — that path is unrelated to everything below and is covered in [operations.md](operations.md).

## 0. Prerequisites

- A GCP project with billing enabled. `infra/terraform.tfvars` is the per-deploy config: `project_id`, `region`, `db_password`, `gcs_bucket` (must be a globally-unique bucket name), and `lb_domain` (leave `""` to use the `.run.app` URLs directly — the documented hackathon-demo choice; no domain or SSL cert needed, see `infra/lb.tf`).
- `gcloud` CLI, authenticated (`gcloud auth login` + `gcloud config set project <id>`) and with Application Default Credentials for Terraform's `google` provider (`gcloud auth application-default login`).
- `terraform` >= the `~> 6.0` google provider constraint in `infra/providers.tf`.
- `python3` with the `cryptography` package installed (for `infra/seed-secrets.sh`, which generates the Fernet key and HMAC secrets locally before pushing them to Secret Manager).
- A Gemini API key (`infra/seed-secrets.sh` seeds it as a fallback secret; see [configuration.md](configuration.md) for why it's a fallback and not the primary auth path).
- Docker is **not** required locally — every image builds remotely via Cloud Build (`infra/build-images.sh` / `cloudbuild.yaml`).

Enable the APIs the resources below need, once per project (derived from the resource types in `infra/main.tf` / `infra/lb.tf`; `servicenetworking` is the one explicitly referenced in `main.tf` for the Cloud SQL private-IP peering):

```bash
gcloud services enable \
  compute.googleapis.com \
  servicenetworking.googleapis.com \
  sqladmin.googleapis.com \
  redis.googleapis.com \
  file.googleapis.com \
  storage.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  vpcaccess.googleapis.com \
  aiplatform.googleapis.com \
  --project=<PROJECT_ID>
```

`aiplatform.googleapis.com` (Vertex AI) is called out separately in `robofleet/llm/providers/cloudrun_jobs.py`'s comments as required for the agent Jobs' primary auth path (see step 6).

## 1. Terraform apply

```bash
cd infra
terraform init
terraform plan
terraform apply
```

This provisions (from `infra/main.tf` + `infra/lb.tf` — exact resource inventory, no LB unless `lb_domain` is set):

- `google_compute_network.robofleet` — the `robofleet-net` VPC.
- `google_sql_database_instance.robofleet` — Postgres 16, tier `db-custom-2-7680` (2 vCPU / 7680 MB), `ENTERPRISE` edition, `REGIONAL` (HA) availability, 20 GB disk, private IP only (`ipv4_enabled = false`), daily backups on.
- `google_redis_instance.robofleet` — Memorystore, `BASIC` tier, 1 GB, Redis 7.0, **no AUTH** (`auth_enabled = false` — private-VPC-only containment, see the `ponytail:` comment in `main.tf`), private service access.
- `google_filestore_instance.robofleet` — `BASIC_HDD`, 1024 GB (the tier's minimum — `variables.tf`'s `filestore_capacity_gb` default), the shared NFS volume every agent Job mounts its workspace from.
- `google_storage_bucket.robofleet` — the GCS bucket named by `var.gcs_bucket`.
- `google_artifact_registry_repository.robofleet` — Docker repo, default id `robo-fleet`.
- `google_secret_manager_secret.keys` — 6 empty secret shells (values come from step 3): `<prefix>-fernet-key`, `-agent-auth-secret`, `-cloud-auth-secret`, `-gemini-api-key`, `-database-password`, `-cloud-auth-password`.
- `google_vpc_access_connector.robofleet` — `robofleet-connector`, `e2-standard-4`, min 2 / max 3 instances. Always created; every Cloud Run service/Job manifest references it by name.
- Private Service Access peering (`google_compute_global_address` + `google_service_networking_connection`) so Cloud SQL and Memorystore have routable private IPs.
- Optionally (only if `lb_domain` is non-empty): a global HTTPS load balancer fronting both Cloud Run services with `/api/*` + `/ws/*` routed to the orchestrator and everything else to the panel. Skipped entirely on the hackathon-demo default.

Read the values the next steps need:

```bash
terraform output cloudsql_connection_name
terraform output cloudsql_private_ip
terraform output memorystore_host
terraform output filestore_ip
terraform output filestore_share
terraform output gcs_bucket
terraform output artifact_registry_repo
terraform output vpc_connector_name
```

`infra/deploy-orchestrator.sh` reads every one of these from `terraform output` itself — you don't need to copy them by hand for that step, but they're useful to sanity-check the deploy and to fill `.env.gcp`.

## 2. Grant IAM roles (not scripted — do this once)

Nothing in this repo's scripts or Terraform grants IAM roles beyond the `allUsers: roles/run.invoker` bindings in step 5/6 (public HTTP access). Two things the code genuinely needs are left to the operator:

1. **The Cloud Run runtime service account** — no `serviceAccountName` is set in `infra/orchestrator-service.yaml`, `panel-service.yaml`, or `agent-job-template.yaml`, so every service/Job runs as the project's **default compute service account** (`<PROJECT_NUMBER>-compute@developer.gserviceaccount.com`). It needs:
   - `roles/secretmanager.admin` (or a custom role covering `secrets.create`/`versions.add`/`versions.destroy`/`versions.list`) — the orchestrator reads the 6 seeded secrets AND mints/rotates a fresh per-agent secret on every spawn (`_rotate_secret` in `robofleet/llm/providers/cloudrun_jobs.py`), which is more than plain `secretAccessor` covers.
   - `roles/run.developer` (or `roles/run.admin`) — the orchestrator creates and executes Cloud Run Jobs for every agent spawn.
   - `roles/aiplatform.user` — agent Jobs call Vertex AI directly via the runtime SA's ADC (see step 6).
   - `roles/storage.objectAdmin` on the GCS bucket — per-agent tool manifests are uploaded there at spawn time.
2. **Cloud Build's own service account** needs the standard `roles/artifactregistry.writer` on the target repo (usually already granted by default in a fresh project when Artifact Registry is enabled before the first build — verify with a fresh `gcloud builds submit` if step 4 fails on push).

```bash
PROJECT_NUMBER=$(gcloud projects describe <PROJECT_ID> --format='value(projectNumber)')
SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
for ROLE in roles/secretmanager.admin roles/run.developer roles/aiplatform.user roles/storage.objectAdmin; do
  gcloud projects add-iam-policy-binding <PROJECT_ID> \
    --member="serviceAccount:${SA}" --role="${ROLE}"
done
```

## 3. Seed secrets

```bash
export ROBOFLEET_GEMINI_API_KEY=<your-gemini-api-key>
export ROBOFLEET_DATABASE_PASSWORD=<same value as infra/terraform.tfvars db_password>
./infra/seed-secrets.sh <PROJECT_ID>
```

This generates and pushes: a Fernet key, an agent-auth HMAC secret, a cloud-auth JWT secret, your Gemini API key, the DB password, and a random CEO login password — six `gcloud secrets versions add` calls under the `robofleet-*` prefix (override with `ROBOFLEET_SECRET_PREFIX`). Read the generated CEO password back later with:

```bash
gcloud secrets versions access latest --secret=robofleet-cloud-auth-password --project=<PROJECT_ID>
```

## 4. Build images (Cloud Build)

The panel's `/api`, `/ws`, `/health` rewrites are resolved at **build time**, so the orchestrator's public URL must be known before this step — but Cloud Run v2 URLs are deterministic from the project number, so you can compute it before the orchestrator service exists:

```bash
export ROBOFLEET_GCP_PROJECT_ID=<PROJECT_ID>
export ROBOFLEET_GCP_REGION=<REGION>
export ROBOFLEET_GCP_ARTIFACT_REGISTRY_REPO=robo-fleet   # or your terraform output value
PROJECT_NUMBER=$(gcloud projects describe "$ROBOFLEET_GCP_PROJECT_ID" --format='value(projectNumber)')
export ROBOFLEET_API_URL="https://robofleet-orchestrator-${PROJECT_NUMBER}.${ROBOFLEET_GCP_REGION}.run.app"
./infra/build-images.sh
```

This runs `gcloud builds submit . --config cloudbuild.yaml` with those substitutions, building and pushing three images, each tagged both `:<short-sha>` and `:latest`: `robofleet-orchestrator`, `robofleet-panel`, `robofleet-agent-adk` (the single ADK+Gemini agent runtime image — see `docker/agent-adk.Dockerfile`; every agent role runs this same image, with role behavior coming from the per-spawn tool manifest, not a different Dockerfile).

## 5. Deploy the orchestrator

```bash
export ROBOFLEET_GCP_PROJECT_ID=<PROJECT_ID>
export ROBOFLEET_GCP_REGION=<REGION>
export ROBOFLEET_GCP_ARTIFACT_REGISTRY_REPO=robo-fleet
export ROBOFLEET_CLOUD_AUTH_EMAIL=<ceo-login-email>
./infra/deploy-orchestrator.sh
```

`infra/deploy-orchestrator.sh` pulls every infra reference from `terraform output` itself, sed-substitutes the `__PLACEHOLDER__` tokens in `infra/orchestrator-service.yaml` into a temp file, and runs `gcloud run services replace` on it, then grants `allUsers: roles/run.invoker` (the platform-level gate — cloud auth + the agent HMAC token are the real application-level gates; see the script's own comments). Boot-healthy in one call: the 6 secrets are inline `secretKeyRef`s in the manifest, so no follow-up `--update-env-vars`/`--set-secrets` step is needed. **This step also applies the database schema** — see "Migrations" below.

## 6. Deploy the panel

```bash
export ROBOFLEET_GCP_PROJECT_ID=<PROJECT_ID>
export ROBOFLEET_GCP_REGION=<REGION>
export ROBOFLEET_GCP_ARTIFACT_REGISTRY_REPO=robo-fleet
./infra/deploy-panel.sh
```

Discovers the orchestrator's URL via `gcloud run services describe robofleet-orchestrator`, substitutes it into `infra/panel-service.yaml`, and replaces the service. The panel is stateless (no DB/Redis/Filestore) — it only proxies `/api/*` and `/ws/*` to the orchestrator.

## Migrations: automatic, not a separate step

There is no `alembic upgrade head` you need to run against Cloud SQL by hand. `robofleet/api/app.py`'s FastAPI `lifespan` calls `init_db()` (`robofleet/db/base.py`) on **every** orchestrator boot, which runs the full Alembic chain (`command.upgrade(cfg, "head")`, a 300-second budget) against `database_url_sync` — the plain host/port DSN, i.e. the Cloud SQL **private IP** reached over the VPC connector, distinct from the connector-based path the async runtime engine uses for normal queries (see [configuration.md](configuration.md)). It's idempotent (stamps a pre-Alembic schema at its initial revision if needed, then applies only pending migrations) and safe to let run on every future revision.

Verify it happened by tailing the orchestrator's first-revision logs for the exact line the code emits:

```bash
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="robofleet-orchestrator"' \
  --project=<PROJECT_ID> --limit=200 --format='value(textPayload)' | grep -i "Alembic upgrade"
```

If you ever need to force a fresh run against a stopped or wedged instance without a full redeploy, the migration only requires network reachability to the private IP plus `ROBOFLEET_DATABASE_*` — a throwaway `gcloud run jobs execute` of the orchestrator image on the same VPC connector, running `alembic upgrade head` as its command, works without touching the live service.

## 7. Verify the stack is up

```bash
ORCH_URL=$(gcloud run services describe robofleet-orchestrator --region=<REGION> --project=<PROJECT_ID> --format='value(status.url)')
PANEL_URL=$(gcloud run services describe robofleet-panel --region=<REGION> --project=<PROJECT_ID> --format='value(status.url)')
curl -fsS "${ORCH_URL}/health"              # liveness, no /api prefix
curl -fsS "${ORCH_URL}/ready"               # DB + Redis connectivity
curl -fsS "${PANEL_URL}/api/auth/status"    # {"cloud_auth_enabled": true} — proxied through the panel to the orchestrator
```

`/health` and `/ready` are mounted at the root (no `/api` prefix) — `GET /api/health` genuinely 404s. `/api/auth/status` is always mounted, unauthenticated, regardless of `ROBOFLEET_AGENT_AUTH_REQUIRED` (`robofleet/api/auth/routes.py`), so it's a reliable second probe that also exercises the panel's rewrite proxy end to end.

## 8. First login

Open the panel URL in a browser. With `ROBOFLEET_CLOUD_AUTH_ENABLED=true` (the GCP default — armed in `infra/orchestrator-service.yaml`), the panel's own middleware (`proxy.ts`) redirects to `/login`. Sign in with `ROBOFLEET_CLOUD_AUTH_EMAIL` (what you passed in step 5) and the password read back from `robofleet-cloud-auth-password` in step 3. Under the hood this is `POST /api/auth/login` (FastAPI Users' cookie auth router, form-encoded `username`/`password`), which sets a signed session cookie — see `robofleet/api/auth/routes.py` / `robofleet/api/auth/seed.py`. There is no registration route; exactly one login user is ever seeded, keyed by a fixed primary key so changing the email later renames the row instead of creating a second user.

## Compliance self-check

`tests/compliance/test_hackathon_stack.py` asserts the mandatory stack pieces are actually wired (ADK importable, the agent entrypoint resolves a `gemini-3.5-*` model id, `async_engine_for_cloudsql` is callable and `get_engine` routes through it when `gcp_cloudsql_instance` is armed):

```bash
uv run pytest tests/compliance/ -v
```

Its one live-GCP assertion is skipped unless `ROBOFLEET_GCP_E2E=1` is set against the deployed stack.

## Which compose files matter here

`docker-compose.yml` / `docker-compose.yaml` (identical, kept in sync by `make compose-sync`) and `docker-compose.registry.yml` are the **local/self-hosted deploy path** — `make dev`, `make infra`, and `make quickstart` (`scripts/bootstrap.sh`) all run through them. They spin up Postgres, Redis, Ollama, and Claude-Code-CLI-based agent containers over a docker socket. **None of it applies to the GCP path above** — Cloud Run has no docker socket, so agents there run as Cloud Run Job executions of the single `robofleet-agent-adk` image instead, and the data plane is Cloud SQL/Memorystore/Filestore, not the compose-managed containers. Both deploy shapes read the same `robofleet/config.py`, just different subsets of it (see [configuration.md](configuration.md)).
