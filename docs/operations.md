# Operating the GCP deploy day to day

This covers the deployed stack from [deploy.md](deploy.md): pausing/reviving it around a recording session, what actually drives the bill, how to check it's alive, where logs live, and how to actually stop spending. For the settings referenced below, see [configuration.md](configuration.md).

## Pause / revive cycle

Two scripts, both project-specific (they hardcode `robofleet-pg`/`robofleet-cache`/`robofleet-orchestrator`/`robofleet-panel` and the `us-central1` region — edit them if you deployed under different names).

### `infra/pause.sh` — back to the idle floor after a session

```bash
./infra/pause.sh
```

What it actually does, in order:

1. `gcloud run services update robofleet-orchestrator --min-instances=0` — scales the orchestrator to zero (no idle compute cost; it cold-starts on the next request).
2. Same for `robofleet-panel`.
3. `gcloud sql instances patch robofleet-pg --activation-policy=NEVER` — **stops** the Cloud SQL instance (compute billing stops; the 20 GB disk + backups keep billing at storage rates — the data is not deleted).
4. `gcloud redis instances delete robofleet-cache` — **deletes** the Memorystore instance outright, not just scales it down. Redis here is cache/rate-limit-state/event-bus, never the system of record (Postgres is), so this is safe — but it means every revive gets a brand-new empty Redis.
5. Lists any still-running Cloud Run Job executions (`gcloud run jobs executions list --filter="status.runningCount>0"`) — informational only, does **not** cancel them.

**What it does NOT touch** — and this matters for the actual bill: Filestore (1024 GB `BASIC_HDD`, provisioned by Terraform, min tier size) and the Serverless VPC Access connector (`e2-standard-4` x 2 min instances) keep running and billing 24/7 regardless of `pause.sh`. Neither script ever deletes or recreates either. See "Stopping spend completely" below.

### `infra/revive-for-take.sh` — bring it back up for a recording session

```bash
./infra/revive-for-take.sh
```

1. Restarts Cloud SQL (`activation-policy=ALWAYS`, ~2 min).
2. **Recreates** Memorystore from scratch (1 GB, `BASIC` tier, `redis_7_0`, `PRIVATE_SERVICE_ACCESS` — no `--enable-auth`, matching `infra/main.tf`'s `auth_enabled = false`), then reads its new private IP back with `gcloud redis instances describe`.
3. Updates the orchestrator with the new Redis host **and deliberately switches off the VPC connector for this session**: `--clear-vpc-connector --network=robofleet-net --subnet=robofleet-net --vpc-egress=private-ranges-only` (Direct VPC egress, which the script's own comment notes is free, unlike the connector's standing per-instance cost) — plus `--min-instances=1` so it's warm for the recording, no cold start.
4. Same `--min-instances=1` for the panel.
5. Sleeps 20s, then curls the orchestrator's `/health` and the panel's `/api/auth/status` — **using hardcoded URLs specific to the `robofleet-deploy` project** (`https://robofleet-orchestrator-813757481440.us-central1.run.app` and a fixed panel `.run.app` host). On a different project, replace those two lines with `gcloud run services describe robofleet-orchestrator --region=us-central1 --format='value(status.url)'` (and the panel equivalent).

The script's own comment states the running cost while up: **Cloud SQL ~EUR0.25/h + Redis ~EUR0.05/h + Cloud Run ~EUR0.05/h** — these are the script author's own estimates, not verified against a live invoice; treat them as ballpark for "how long can I leave this up for a recording" planning. `infra/pause.sh`'s own comment states the floor it returns to: **~EUR0.15/day** — that number, by the reasoning above, only accounts for the Cloud SQL-stopped + Redis-deleted state; it does not include whatever Filestore + the VPC connector cost while they sit idle (the scripts don't state a number for those, and this file doesn't invent one).

Run `pause.sh` again once you're done recording.

## The real cost drivers (resource inventory, from `infra/main.tf` + `infra/lb.tf`)

| Resource | Tier / size | Touched by pause.sh? | Touched by revive-for-take.sh? |
|---|---|---|---|
| Cloud SQL (`robofleet-pg`) | `db-custom-2-7680` (2 vCPU / 7.5 GB), `ENTERPRISE`, `REGIONAL` (HA — the single largest line item in the tier list), 20 GB disk | Stopped (compute billing off) | Restarted |
| Memorystore (`robofleet-cache`) | `BASIC`, 1 GB, Redis 7.0, no AUTH | Deleted | Recreated |
| Filestore (`robofleet-workspaces`) | `BASIC_HDD`, 1024 GB (the tier's minimum size) | **Not touched — bills continuously** | Not touched |
| VPC Access connector (`robofleet-connector`) | `e2-standard-4`, min 2 / max 3 instances, always-on | **Not touched — bills continuously** | Bypassed for that session (Direct VPC egress instead), but the connector resource itself is still provisioned and billing |
| Cloud Run services (orchestrator + panel) | scale-to-zero capable, 2Gi/2CPU on the orchestrator (no explicit limit on the panel, so Cloud Run's default applies) | Scaled to `min-instances=0` | Scaled to `min-instances=1` |
| Artifact Registry + GCS bucket | storage only | Not touched | Not touched |
| Cloud Run Jobs (agents) | 1Gi CPU / 2Gi memory per execution, billed only while a Job execution runs | N/A (pay-per-execution) | N/A |

The two always-on infrastructure pieces — **Filestore and the VPC connector** — are the standing cost floor neither pause script addresses. If the goal is genuinely zero spend between sessions rather than the documented ~EUR0.15/day floor, see "Stopping spend completely" below.

## Checking the stack is up

Same probes as [deploy.md](deploy.md)'s verify step:

```bash
ORCH_URL=$(gcloud run services describe robofleet-orchestrator --region=<REGION> --project=<PROJECT_ID> --format='value(status.url)')
PANEL_URL=$(gcloud run services describe robofleet-panel --region=<REGION> --project=<PROJECT_ID> --format='value(status.url)')
curl -fsS "${ORCH_URL}/health"              # liveness only
curl -fsS "${ORCH_URL}/ready"               # {"status": "ok"|"degraded", "database": ..., "redis": ...}
curl -fsS "${PANEL_URL}/api/auth/status"    # proxied through the panel; exercises the whole rewrite chain
```

`/ready` (`robofleet/api/routes/health.py`) actually pings Postgres and Redis and reports `degraded` if either fails — the more useful check after a revive, since a paused-then-revived Redis is a fresh empty instance and a bad host substitution would show up here first.

## Where logs live

Every Cloud Run service and Job execution writes to Cloud Logging automatically — no separate log shipping to configure. Read them with:

```bash
# Orchestrator (or swap the service_name for robofleet-panel)
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="robofleet-orchestrator"' \
  --project=<PROJECT_ID> --limit=100 --format='value(timestamp,textPayload)'

# One agent's Cloud Run Job execution (job names are robofleet-agent-<slug>)
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="robofleet-agent-<slug>"' \
  --project=<PROJECT_ID> --limit=100 --format='value(timestamp,textPayload)'
```

Or use the Cloud Console's Logs Explorer with the same resource-type filters. The orchestrator's own structured logs (via `structlog`) include the "Alembic upgrade finished" boot line (see deploy.md's migrations section) and every agent-spawn/reap/dispatch event.

## Stopping spend completely

`infra/pause.sh` gets you to the documented ~EUR0.15/day floor (Cloud SQL stopped, Redis deleted, both Cloud Run services at zero instances) — it does **not** stop Filestore or VPC-connector billing, since neither script deletes them. To actually get to zero between demo sessions, either:

- Manually delete/recreate Filestore and the VPC connector around each session the same way `revive-for-take.sh` already does for Redis (not scripted in this repo — you'd be writing the Filestore/connector equivalent yourself), or
- Tear down everything Terraform created:

  ```bash
  cd infra
  terraform destroy
  ```

This is destructive — it deletes the Cloud SQL instance (and its data; `deletion_protection = false` in `infra/main.tf` means Terraform will not refuse), Filestore (and every agent workspace clone on it), the GCS bucket, the VPC connector, and the Secret Manager secret shells. Re-provisioning afterward means re-running the full [deploy.md](deploy.md) sequence from step 1, including re-seeding secrets. Do this only between demo takes you're genuinely done with, not as a nightly routine.

## Which compose files are for local use only

`docker-compose.yml` / `docker-compose.yaml` / `docker-compose.registry.yml` and `scripts/bootstrap.sh` (`make quickstart`) are the self-hosted, no-GCP-account alternative — unrelated to everything above. See [deploy.md](deploy.md)'s "Which compose files matter here" for the full split.
