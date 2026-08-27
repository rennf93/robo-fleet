#!/usr/bin/env bash
# Seed the six RoboFleet Secret Manager secrets for one GCP project.
# Usage: ./infra/seed-secrets.sh PROJECT_ID
# Requires: gcloud (authed), python3 with `cryptography` installed.
# Env overrides:
#   ROBOFLEET_SECRET_PREFIX (default robo-fleet) - prefix for secret ids
#   ROBOFLEET_GEMINI_API_KEY (required) - Gemini API key to store
#   ROBOFLEET_DATABASE_PASSWORD (required) - Cloud SQL user password to store
# The CEO login password is generated here; read it back with
#   gcloud secrets versions access latest --secret=robofleet-cloud-auth-password
set -euo pipefail

PROJECT="${1:?usage: seed-secrets.sh PROJECT_ID}"
PREFIX="${ROBOFLEET_SECRET_PREFIX:-robofleet}"

put() {
  gcloud secrets versions add "${PREFIX}-$1" --data-file=- --project="$PROJECT"
}

printf '%s' "$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")" | put fernet-key
printf '%s' "$(python -c "import secrets; print(secrets.token_urlsafe(48))")" | put agent-auth-secret
printf '%s' "$(python -c "import secrets; print(secrets.token_urlsafe(48))")" | put cloud-auth-secret
printf '%s' "${ROBOFLEET_GEMINI_API_KEY:?set ROBOFLEET_GEMINI_API_KEY}" | put gemini-api-key
printf '%s' "${ROBOFLEET_DATABASE_PASSWORD:?set ROBOFLEET_DATABASE_PASSWORD}" | put database-password
printf '%s' "$(python -c "import secrets; print(secrets.token_urlsafe(24))")" | put cloud-auth-password

echo "Seeded 6 secrets under prefix ${PREFIX}- in project ${PROJECT}."