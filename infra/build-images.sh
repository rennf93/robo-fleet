#!/usr/bin/env bash
# Build the three RoboFleet images via Cloud Build into Artifact Registry.
# Reads project/region/repo from ROBOFLEET_GCP_* env vars (no hardcoded values).
# Requires: gcloud (authed to the target project).
# Env:
#   ROBOFLEET_GCP_PROJECT_ID (required)
#   ROBOFLEET_GCP_REGION     (required)
#   ROBOFLEET_GCP_ARTIFACT_REGISTRY_REPO (default robo-fleet)
#   ROBOFLEET_API_URL        (required: the orchestrator's public Cloud Run URL,
#                             baked into the panel's build-time /api, /ws and
#                             /health rewrites; an empty value re-creates the
#                             localhost:8000 bug)
set -euo pipefail

PROJECT="${ROBOFLEET_GCP_PROJECT_ID:?set ROBOFLEET_GCP_PROJECT_ID}"
REGION="${ROBOFLEET_GCP_REGION:?set ROBOFLEET_GCP_REGION}"
REPO="${ROBOFLEET_GCP_ARTIFACT_REGISTRY_REPO:-robo-fleet}"
AR_HOST="${REGION}-docker.pkg.dev"

cd "$(dirname "$0")/.."

echo "Submitting Cloud Build to project ${PROJECT}, region ${REGION}, repo ${REPO}."
gcloud builds submit . \
  --config cloudbuild.yaml \
  --project="${PROJECT}" \
  --substitutions=_AR_HOST="${AR_HOST}",_AR_REPO="${REPO}",_PROJECT_ID="${PROJECT}",_SHORT_SHA="$(git rev-parse --short HEAD)",_API_URL="${ROBOFLEET_API_URL:?set ROBOFLEET_API_URL to the orchestrator's public URL}"

echo "Built robofleet-orchestrator, robofleet-panel, robofleet-agent-adk into ${AR_HOST}/${PROJECT}/${REPO}."