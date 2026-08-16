#!/usr/bin/env bash
# Deploy roboco-panel to Cloud Run.
# Reads project/region/repo from ROBOCO_GCP_* env vars (no hardcoded values).
# Discovers the orchestrator's Cloud Run URL from the already-deployed
# roboco-orchestrator service, sed-substitutes __PLACEHOLDER__ tokens in
# panel-service.yaml into a temp copy, and calls `gcloud run services replace`.
#
# Requires: gcloud (authed), roboco-orchestrator already deployed.
# Env (required):
#   ROBOCO_GCP_PROJECT_ID
#   ROBOCO_GCP_REGION
#   ROBOCO_GCP_ARTIFACT_REGISTRY_REPO (default robo-fleet)
#   ROBOCO_CLOUD_AUTH_EMAIL     (seeded CEO login)
#   ROBOCO_CLOUD_AUTH_PASSWORD  (seeded CEO login password)
# Env (optional):
#   ROBOCO_PUBLIC_BASE_URL (default https://roboco.run.app)
set -euo pipefail

PROJECT="${ROBOCO_GCP_PROJECT_ID:?set ROBOCO_GCP_PROJECT_ID}"
REGION="${ROBOCO_GCP_REGION:?set ROBOCO_GCP_REGION}"
REPO="${ROBOCO_GCP_ARTIFACT_REGISTRY_REPO:-robo-fleet}"
PUBLIC_BASE_URL="${ROBOCO_PUBLIC_BASE_URL:-https://roboco.run.app}"
AR_HOST="${REGION}-docker.pkg.dev"

cd "$(dirname "$0")/.."

# --- Discover the orchestrator's Cloud Run URL ---
ORCHESTRATOR_URL="$(gcloud run services describe roboco-orchestrator \
  --region="${REGION}" \
  --project="${PROJECT}" \
  --format='value(status.url)')"
echo "Orchestrator URL: ${ORCHESTRATOR_URL}"

# --- Substitute placeholders into a temp manifest ---
TMP_MANIFEST="$(mktemp --suffix=.yaml)"
trap 'rm -f "${TMP_MANIFEST}"' EXIT

sed \
  -e "s|__AR_HOST__|${AR_HOST}|g" \
  -e "s|__PROJECT_ID__|${PROJECT}|g" \
  -e "s|__AR_REPO__|${REPO}|g" \
  -e "s|__ORCHESTRATOR_URL__|${ORCHESTRATOR_URL}|g" \
  -e "s|__PUBLIC_BASE_URL__|${PUBLIC_BASE_URL}|g" \
  infra/panel-service.yaml > "${TMP_MANIFEST}"

echo "Replacing roboco-panel service..."
gcloud run services replace "${TMP_MANIFEST}" \
  --region="${REGION}" \
  --project="${PROJECT}"

# --- Set cloud auth creds via env vars (not in Secret Manager's 4-seed set) ---
echo "Updating env vars (cloud auth creds)..."
gcloud run services update roboco-panel \
  --region="${REGION}" \
  --project="${PROJECT}" \
  --update-env-vars="^@^ROBOCO_CLOUD_AUTH_EMAIL=${ROBOCO_CLOUD_AUTH_EMAIL:?set ROBOCO_CLOUD_AUTH_EMAIL}@ROBOCO_CLOUD_AUTH_PASSWORD=${ROBOCO_CLOUD_AUTH_PASSWORD:?set ROBOCO_CLOUD_AUTH_PASSWORD}"

echo "Deployed roboco-panel to ${REGION}."
echo "URL: gcloud run services describe roboco-panel --region=${REGION} --project=${PROJECT} --format='value(status.url)'"