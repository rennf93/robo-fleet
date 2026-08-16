#!/usr/bin/env bash
# Deploy roboco-orchestrator to Cloud Run.
# Reads project/region/repo from ROBOCO_GCP_* env vars (no hardcoded values).
# Pulls infra references (Cloud SQL connection name, Memorystore host, Filestore
# IP/share, GCS bucket) from terraform output, sed-substitutes the
# __PLACEHOLDER__ tokens in orchestrator-service.yaml into a temp copy, and
# calls `gcloud run services replace`.
#
# Requires: gcloud (authed), terraform (infra/ applied or at least refreshed).
# Env (required):
#   ROBOCO_GCP_PROJECT_ID
#   ROBOCO_GCP_REGION
#   ROBOCO_GCP_ARTIFACT_REGISTRY_REPO (default robo-fleet)
#   ROBOCO_DATABASE_PASSWORD   (Cloud SQL user password)
#   ROBOCO_REDIS_PASSWORD       (Memorystore AUTH token)
#   ROBOCO_CLOUD_AUTH_EMAIL     (seeded CEO login)
#   ROBOCO_CLOUD_AUTH_PASSWORD  (seeded CEO login password)
# Env (optional):
#   ROBOCO_GCP_VPC_CONNECTOR_NAME (default roboco-connector)
set -euo pipefail

PROJECT="${ROBOCO_GCP_PROJECT_ID:?set ROBOCO_GCP_PROJECT_ID}"
REGION="${ROBOCO_GCP_REGION:?set ROBOCO_GCP_REGION}"
REPO="${ROBOCO_GCP_ARTIFACT_REGISTRY_REPO:-robo-fleet}"
CONNECTOR="${ROBOCO_GCP_VPC_CONNECTOR_NAME:-roboco-connector}"
AR_HOST="${REGION}-docker.pkg.dev"

cd "$(dirname "$0")/.."

# --- Read terraform outputs ---
TF_DIR="infra"
CLOUDSQL_INSTANCE="$(terraform -chdir=${TF_DIR} output -raw cloudsql_connection_name)"
MEMORYSTORE_HOST="$(terraform -chdir=${TF_DIR} output -raw memorystore_host)"
FILESTORE_IP="$(terraform -chdir=${TF_DIR} output -raw filestore_ip)"
FILESTORE_SHARE="$(terraform -chdir=${TF_DIR} output -raw filestore_share)"
GCS_BUCKET="$(terraform -chdir=${TF_DIR} output -raw gcs_bucket)"
VPC_CONNECTOR_PATH="projects/${PROJECT}/regions/${REGION}/connectors/${CONNECTOR}"

echo "terraform outputs:"
echo "  cloudsql:    ${CLOUDSQL_INSTANCE}"
echo "  memorystore: ${MEMORYSTORE_HOST}"
echo "  filestore:   ${FILESTORE_IP}/${FILESTORE_SHARE}"
echo "  gcs bucket:  ${GCS_BUCKET}"
echo "  vpc conn:    ${VPC_CONNECTOR_PATH}"

# --- Substitute placeholders into a temp manifest ---
TMP_MANIFEST="$(mktemp --suffix=.yaml)"
trap 'rm -f "${TMP_MANIFEST}"' EXIT

sed \
  -e "s|__PROJECT_ID__|${PROJECT}|g" \
  -e "s|__REGION__|${REGION}|g" \
  -e "s|__AR_HOST__|${AR_HOST}|g" \
  -e "s|__AR_REPO__|${REPO}|g" \
  -e "s|__CLOUDSQL_INSTANCE__|${CLOUDSQL_INSTANCE}|g" \
  -e "s|__MEMORYSTORE_HOST__|${MEMORYSTORE_HOST}|g" \
  -e "s|__FILESTORE_IP__|${FILESTORE_IP}|g" \
  -e "s|__FILESTORE_SHARE__|${FILESTORE_SHARE}|g" \
  -e "s|__GCS_BUCKET__|${GCS_BUCKET}|g" \
  -e "s|__VPC_CONNECTOR_PATH__|${VPC_CONNECTOR_PATH}|g" \
  "${TF_DIR}/orchestrator-service.yaml" > "${TMP_MANIFEST}"

echo "Replacing roboco-orchestrator service..."
gcloud run services replace "${TMP_MANIFEST}" \
  --region="${REGION}" \
  --project="${PROJECT}"

# --- Set the non-Secret-Manager passwords + cloud auth creds via env vars ---
# These are not in the 4-seed Secret Manager set; they are set as plaintext env
# vars. For a production deploy, move them into Secret Manager and switch the
# manifest to secretRef.
echo "Updating env vars (passwords, cloud auth creds)..."
gcloud run services update roboco-orchestrator \
  --region="${REGION}" \
  --project="${PROJECT}" \
  --update-env-vars="^@^ROBOCO_DATABASE_PASSWORD=${ROBOCO_DATABASE_PASSWORD:?set ROBOCO_DATABASE_PASSWORD}@ROBOCO_REDIS_PASSWORD=${ROBOCO_REDIS_PASSWORD:?set ROBOCO_REDIS_PASSWORD}@ROBOCO_CLOUD_AUTH_EMAIL=${ROBOCO_CLOUD_AUTH_EMAIL:?set ROBOCO_CLOUD_AUTH_EMAIL}@ROBOCO_CLOUD_AUTH_PASSWORD=${ROBOCO_CLOUD_AUTH_PASSWORD:?set ROBOCO_CLOUD_AUTH_PASSWORD}"

echo "Deployed roboco-orchestrator to ${REGION}."
echo "Verify: gcloud run services describe roboco-orchestrator --region=${REGION} --project=${PROJECT}"
echo "Health: gcloud run services describe roboco-orchestrator --region=${REGION} --project=${PROJECT} --format='value(status.url)'"