#!/usr/bin/env bash
# Seed the four RoboCo Secret Manager secrets for one GCP project.
# Usage: ./infra/seed-secrets.sh PROJECT_ID
# Requires: gcloud (authed), python3 with `cryptography` installed.
# Env overrides:
#   ROBOCO_SECRET_PREFIX (default roboco) - prefix for secret ids
#   ROBOCO_GEMINI_API_KEY (required) - Gemini API key to store
set -euo pipefail

PROJECT="${1:?usage: seed-secrets.sh PROJECT_ID}"
PREFIX="${ROBOCO_SECRET_PREFIX:-roboco}"

put() {
  gcloud secrets versions add "${PREFIX}-$1" --data-file=- --project="$PROJECT"
}

printf '%s' "$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")" | put fernet-key
printf '%s' "$(python -c "import secrets; print(secrets.token_urlsafe(48))")" | put agent-auth-secret
printf '%s' "$(python -c "import secrets; print(secrets.token_urlsafe(48))")" | put cloud-auth-secret
printf '%s' "${ROBOCO_GEMINI_API_KEY:?set ROBOCO_GEMINI_API_KEY}" | put gemini-api-key

echo "Seeded 4 secrets under prefix ${PREFIX}- in project ${PROJECT}."