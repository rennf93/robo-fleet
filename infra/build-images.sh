#!/usr/bin/env bash
# Build the three RoboFleet images via Cloud Build into Artifact Registry.
# Reads project/region/repo from ROBOFLEET_GCP_* env vars (no hardcoded values).
# Requires: gcloud (authed to the target project).
# Env:
#   ROBOFLEET_GCP_PROJECT_ID (required)
#   ROBOFLEET_GCP_REGION     (required)
#   ROBOFLEET_GCP_ARTIFACT_REGISTRY_REPO (default robo-fleet)
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
  --substitutions=_AR_HOST="${AR_HOST}",_AR_REPO="${REPO}"

echo "Built robofleet-orchestrator, robofleet-panel, robofleet-agent-adk into ${AR_HOST}/${PROJECT}/${REPO}."