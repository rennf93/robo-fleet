#!/usr/bin/env bash
# Deploy robofleet-panel to Cloud Run.
# Reads project/region/repo from ROBOFLEET_GCP_* env vars (no hardcoded values).
# Discovers the orchestrator's Cloud Run URL from the already-deployed
# robofleet-orchestrator service, sed-substitutes __PLACEHOLDER__ tokens in
# panel-service.yaml into a temp copy, and calls `gcloud run services replace`.
#
# Requires: gcloud (authed), robofleet-orchestrator already deployed.
# Env (required):
#   ROBOFLEET_GCP_PROJECT_ID
#   ROBOFLEET_GCP_REGION
#   ROBOFLEET_GCP_ARTIFACT_REGISTRY_REPO (default robo-fleet)
# Env (optional):
#   ROBOFLEET_PUBLIC_BASE_URL (default https://robo-fleet.run.app)
#
# The panel (Next.js) does NOT carry the cloud-auth secret, email, or
# password: those are orchestrator-side (Python, JWT signing + CEO seed). The
# panel forwards the browser's session cookie to the orchestrator via the
# next.config rewrite proxy, so a single `gcloud run services replace` is a
# boot-healthy deploy with no post-replace env step.
set -euo pipefail

PROJECT="${ROBOFLEET_GCP_PROJECT_ID:?set ROBOFLEET_GCP_PROJECT_ID}"
REGION="${ROBOFLEET_GCP_REGION:?set ROBOFLEET_GCP_REGION}"
REPO="${ROBOFLEET_GCP_ARTIFACT_REGISTRY_REPO:-robo-fleet}"
PUBLIC_BASE_URL="${ROBOFLEET_PUBLIC_BASE_URL:-https://robo-fleet.run.app}"
AR_HOST="${REGION}-docker.pkg.dev"

cd "$(dirname "$0")/.."

# --- Discover the orchestrator's Cloud Run URL ---
ORCHESTRATOR_URL="$(gcloud run services describe robofleet-orchestrator \
  --region="${REGION}" \
  --project="${PROJECT}" \
  --format='value(status.url)')"
echo "Orchestrator URL: ${ORCHESTRATOR_URL}"

# --- Substitute placeholders into a temp manifest ---
TMP_MANIFEST="$(mktemp)"
trap 'rm -f "${TMP_MANIFEST}"' EXIT

sed \
  -e "s|__AR_HOST__|${AR_HOST}|g" \
  -e "s|__PROJECT_ID__|${PROJECT}|g" \
  -e "s|__AR_REPO__|${REPO}|g" \
  -e "s|__ORCHESTRATOR_URL__|${ORCHESTRATOR_URL}|g" \
  -e "s|__PUBLIC_BASE_URL__|${PUBLIC_BASE_URL}|g" \
  infra/panel-service.yaml > "${TMP_MANIFEST}"

echo "Replacing robofleet-panel service..."
gcloud run services replace "${TMP_MANIFEST}" \
  --region="${REGION}" \
  --project="${PROJECT}"

# --- Allow unauthenticated: the panel is a public UI (the login page must
# load for an unauthed browser). The panel's own middleware (proxy.ts) gates
# the dashboard chrome with a /login redirect, and the orchestrator's cloud
# auth gates every /api/* call the rewrite proxy forwards. IAM
# allUsers:run.invoker only lifts the platform gate so the browser reaches
# the app.
echo "Granting allUsers roles/run.invoker (allow-unauthenticated)..."
gcloud run services add-iam-policy-binding robofleet-panel \
  --member=allUsers \
  --role=roles/run.invoker \
  --region="${REGION}" \
  --project="${PROJECT}" >/dev/null

echo "Deployed robofleet-panel to ${REGION}."
echo "URL: gcloud run services describe robofleet-panel --region=${REGION} --project=${PROJECT} --format='value(status.url)'"