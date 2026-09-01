#!/usr/bin/env bash
# Bring the panel + orchestrator back for a recording session, WITHOUT the
# VPC connector (Direct VPC egress is free) and WITHOUT Filestore (the approve
# beat merges via the GitHub API; no workspace needed). Cost while up:
# SQL ~EUR0.25/h + Redis ~EUR0.05/h + Cloud Run ~EUR0.05/h. Run pause.sh after.
set -eu
R=us-central1
echo "== 1/4 Cloud SQL: start (~2 min)"
gcloud sql instances patch robofleet-pg --activation-policy=ALWAYS --quiet | tail -1
echo "== 2/4 Redis: recreate 1 GB basic (~5 min), then read its new private IP"
gcloud redis instances create robofleet-cache --region=$R --size=1 --tier=basic \
  --redis-version=redis_7_0 --network=projects/robofleet-deploy/global/networks/robofleet-net \
  --connect-mode=PRIVATE_SERVICE_ACCESS --quiet | tail -1 || true
REDIS_IP=$(gcloud redis instances describe robofleet-cache --region=$R --format="value(host)")
echo "redis host: $REDIS_IP"
echo "== 3/4 orchestrator: Direct VPC egress (no connector), new redis host, min 1"
gcloud run services update robofleet-orchestrator --region=$R \
  --clear-vpc-connector --network=robofleet-net --subnet=robofleet-net --vpc-egress=private-ranges-only \
  --update-env-vars=ROBOFLEET_REDIS_HOST=$REDIS_IP --min-instances=1 --quiet | tail -1
echo "== 4/4 panel: min 1"
gcloud run services update robofleet-panel --region=$R --min-instances=1 --quiet | tail -1
echo "== health"
sleep 20
curl -s -o /dev/null -w "orchestrator /health=%{http_code}\n" https://robofleet-orchestrator-813757481440.us-central1.run.app/health
curl -s -o /dev/null -w "panel /api/auth/status=%{http_code}\n" https://robofleet-panel-tfdwkzepca-uc.a.run.app/api/auth/status
echo "READY - record, then run pause.sh"
