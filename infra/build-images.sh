#!/usr/bin/env bash
# Build the three RoboCo images via Cloud Build into Artifact Registry.
# Reads project/region/repo from ROBOCO_GCP_* env vars (no hardcoded values).
# Requires: gcloud (authed to the target project).
# Env:
#   ROBOCO_GCP_PROJECT_ID (required)
#   ROBOCO_GCP_REGION     (required)
#   ROBOCO_GCP_ARTIFACT_REGISTRY_REPO (default robo-fleet)
set -euo pipefail

PROJECT="${ROBOCO_GCP_PROJECT_ID:?set ROBOCO_GCP_PROJECT_ID}"
REGION="${ROBOCO_GCP_REGION:?set ROBOCO_GCP_REGION}"
REPO="${ROBOCO_GCP_ARTIFACT_REGISTRY_REPO:-robo-fleet}"
AR_HOST="${REGION}-docker.pkg.dev"

cd "$(dirname "$0")/.."

echo "Submitting Cloud Build to project ${PROJECT}, region ${REGION}, repo ${REPO}."
gcloud builds submit . \
  --config cloudbuild.yaml \
  --project="${PROJECT}" \
  --substitutions=_AR_HOST="${AR_HOST}",_AR_REPO="${REPO}"

echo "Built roboco-orchestrator, roboco-panel, roboco-agent-adk into ${AR_HOST}/${PROJECT}/${REPO}."