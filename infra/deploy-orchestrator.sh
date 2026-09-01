#!/usr/bin/env bash
# Deploy robofleet-orchestrator to Cloud Run.
# Reads project/region/repo from ROBOFLEET_GCP_* env vars (no hardcoded values).
# Pulls infra references (Cloud SQL connection name, Memorystore host, Filestore
# IP/share, GCS bucket) from terraform output, sed-substitutes the
# __PLACEHOLDER__ tokens in orchestrator-service.yaml into a temp copy, and
# calls `gcloud run services replace`.
#
# Requires: gcloud (authed), terraform (infra/ applied or at least refreshed).
# Env (required):
#   ROBOFLEET_GCP_PROJECT_ID
#   ROBOFLEET_GCP_REGION
#   ROBOFLEET_GCP_ARTIFACT_REGISTRY_REPO (default robo-fleet)
#   ROBOFLEET_REDIS_PASSWORD       (Memorystore AUTH token)
#   ROBOFLEET_CLOUD_AUTH_EMAIL     (seeded CEO login)
# The DB password and the CEO login password are Secret Manager references in
# the manifest (seeded by infra/seed-secrets.sh), not deploy-env inputs.
# Env (optional):
#   ROBOFLEET_GCP_VPC_CONNECTOR_NAME (default robofleet-connector)
set -euo pipefail

PROJECT="${ROBOFLEET_GCP_PROJECT_ID:?set ROBOFLEET_GCP_PROJECT_ID}"
REGION="${ROBOFLEET_GCP_REGION:?set ROBOFLEET_GCP_REGION}"
REPO="${ROBOFLEET_GCP_ARTIFACT_REGISTRY_REPO:-robo-fleet}"
CONNECTOR="${ROBOFLEET_GCP_VPC_CONNECTOR_NAME:-robofleet-connector}"
AR_HOST="${REGION}-docker.pkg.dev"

# Orchestrator self URL: the service's own public Cloud Run URL, derived from
# the project number (stable: https://<svc>-<projnum>.<region>.run.app). The
# manifest sets ROBOFLEET_API_URL / _ORCHESTRATOR_URL to this; the
# orchestrator's internal self-calls AND spawned agent Cloud Run Jobs resolve
# their callback from settings.api_url, so it must be this public URL
# (localhost:8000 is unreachable from a separate agent job container).
PROJECT_NUMBER="$(gcloud projects describe "${PROJECT}" --format='value(projectNumber)')"
ORCH_SELF_URL="https://robofleet-orchestrator-${PROJECT_NUMBER}.${REGION}.run.app"

cd "$(dirname "$0")/.."

# --- Read terraform outputs ---
TF_DIR="infra"
CLOUDSQL_INSTANCE="$(terraform -chdir=${TF_DIR} output -raw cloudsql_connection_name)"
CLOUDSQL_PRIVATE_IP="$(terraform -chdir=${TF_DIR} output -raw cloudsql_private_ip)"
MEMORYSTORE_HOST="$(terraform -chdir=${TF_DIR} output -raw memorystore_host)"
FILESTORE_IP="$(terraform -chdir=${TF_DIR} output -raw filestore_ip)"
FILESTORE_SHARE="$(terraform -chdir=${TF_DIR} output -raw filestore_share)"
GCS_BUCKET="$(terraform -chdir=${TF_DIR} output -raw gcs_bucket)"
VPC_CONNECTOR_PATH="projects/${PROJECT}/locations/${REGION}/connectors/${CONNECTOR}"

echo "terraform outputs:"
echo "  cloudsql:    ${CLOUDSQL_INSTANCE}"
echo "  memorystore: ${MEMORYSTORE_HOST}"
echo "  filestore:   ${FILESTORE_IP}/${FILESTORE_SHARE}"
echo "  gcs bucket:  ${GCS_BUCKET}"
echo "  vpc conn:    ${VPC_CONNECTOR_PATH}"

# --- Substitute placeholders into a temp manifest ---
TMP_MANIFEST="$(mktemp)"
trap 'rm -f "${TMP_MANIFEST}"' EXIT

sed \
  -e "s|__PROJECT_ID__|${PROJECT}|g" \
  -e "s|__REGION__|${REGION}|g" \
  -e "s|__AR_HOST__|${AR_HOST}|g" \
  -e "s|__AR_REPO__|${REPO}|g" \
  -e "s|__CLOUDSQL_INSTANCE__|${CLOUDSQL_INSTANCE}|g" \
  -e "s|__CLOUDSQL_PRIVATE_IP__|${CLOUDSQL_PRIVATE_IP}|g" \
  -e "s|__MEMORYSTORE_HOST__|${MEMORYSTORE_HOST}|g" \
  -e "s|__FILESTORE_IP__|${FILESTORE_IP}|g" \
  -e "s|__FILESTORE_SHARE__|${FILESTORE_SHARE}|g" \
  -e "s|__GCS_BUCKET__|${GCS_BUCKET}|g" \
  -e "s|__VPC_CONNECTOR_PATH__|${VPC_CONNECTOR_PATH}|g" \
  -e "s|__ORCH_SELF_URL__|${ORCH_SELF_URL}|g" \
  -e "s|__CLOUD_AUTH_EMAIL__|${ROBOFLEET_CLOUD_AUTH_EMAIL:?set ROBOFLEET_CLOUD_AUTH_EMAIL}|g" \
  "${TF_DIR}/orchestrator-service.yaml" > "${TMP_MANIFEST}"

echo "Replacing robofleet-orchestrator service..."
gcloud run services replace "${TMP_MANIFEST}" \
  --region="${REGION}" \
  --project="${PROJECT}"

# The cloud-auth email and the 6 Secret Manager secrets (DB password and CEO
# password included) are all inlined in the manifest (placeholders above +
# inline secretKeyRef), so
# a single `gcloud run services replace` deploys a boot-healthy revision. No
# post-replace --update-env-vars / --set-secrets step is needed (and would
# conflict with the inline secretKeyRef entries).

echo "Deployed robofleet-orchestrator to ${REGION}."

# Allow unauthenticated: spawned agent Cloud Run Jobs, the orchestrator's own
# internal self-calls (auto-submit, self-PATCH), and the HTTPS load balancer
# all reach this service over its public URL. Without --allow-unauthenticated
# the Cloud Run IAM gate 403s them before the app layer (cloud auth for humans,
# the HMAC X-Agent-ID token for agents/system) can authenticate. cloud auth +
# HMAC remain the real gates; IAM allUsers:run.invoker only lifts the
# platform-level gate so requests reach the app.
echo "Granting allUsers roles/run.invoker (allow-unauthenticated)..."
gcloud run services add-iam-policy-binding robofleet-orchestrator \
  --member=allUsers \
  --role=roles/run.invoker \
  --region="${REGION}" \
  --project="${PROJECT}" >/dev/null

echo "Deployed robofleet-orchestrator to ${REGION}."
echo "URL: ${ORCH_SELF_URL}"
echo "Verify: gcloud run services describe robofleet-orchestrator --region=${REGION} --project=${PROJECT}"
echo "Health: curl -fsS ${ORCH_SELF_URL}/health"