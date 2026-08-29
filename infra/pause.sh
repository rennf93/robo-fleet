#!/usr/bin/env bash
# Back to ~EUR0.15/day after a recording session (DB data kept).
set -u
R=us-central1
gcloud run services update robofleet-orchestrator --region=$R --min-instances=0 --quiet 2>&1 | tail -1
gcloud run services update robofleet-panel --region=$R --min-instances=0 --quiet 2>&1 | tail -1
gcloud sql instances patch robofleet-pg --activation-policy=NEVER --quiet 2>&1 | tail -1
gcloud redis instances delete robofleet-cache --region=$R --quiet 2>&1 | tail -1
gcloud run jobs executions list --region=$R --filter="status.runningCount>0" --format="value(name)"
echo "PAUSED"
