#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-kof-gcloud}"
REGION="${REGION:-europe-west6}"
FRONTEND_SERVICE="${FRONTEND_SERVICE:-roadshow-frontend}"
BACKEND_SERVICE="${BACKEND_SERVICE:-roadshow-backend}"
ARTIFACT_REPOSITORY="${ARTIFACT_REPOSITORY:-roadshow}"
API_TOKEN_SECRET="${API_TOKEN_SECRET:-roadshow-api-access-token}"
RUNTIME_SERVICE_ACCOUNT="${RUNTIME_SERVICE_ACCOUNT:-}"
IMAGE_TAG="${IMAGE_TAG:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

log() {
  printf '%s\n' "$*"
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command '$1' is not available in PATH."
}

require_command gcloud

if [[ -z "$IMAGE_TAG" ]]; then
  if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    IMAGE_TAG="$(git rev-parse --short HEAD)"
  else
    IMAGE_TAG="$(date +%Y%m%d%H%M%S)"
  fi
fi
if [[ ! "$IMAGE_TAG" =~ ^[A-Za-z0-9_.-]+$ ]]; then
  fail "Image tag '${IMAGE_TAG}' is invalid. Use letters, numbers, underscores, periods, or dashes."
fi

ACTIVE_ACCOUNT="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' | head -n 1)"
if [[ -z "$ACTIVE_ACCOUNT" ]]; then
  fail "No active gcloud account. Run 'gcloud auth login' or use Google Cloud Shell."
fi

log "Using project ${PROJECT_ID} in ${REGION} as ${ACTIVE_ACCOUNT}."
gcloud config set project "$PROJECT_ID" >/dev/null

log "Ensuring required Google Cloud APIs are enabled."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  --project "$PROJECT_ID" >/dev/null

if ! gcloud artifacts repositories describe "$ARTIFACT_REPOSITORY" \
  --location "$REGION" \
  --project "$PROJECT_ID" >/dev/null 2>&1; then
  log "Creating Artifact Registry repository ${ARTIFACT_REPOSITORY}."
  gcloud artifacts repositories create "$ARTIFACT_REPOSITORY" \
    --repository-format docker \
    --location "$REGION" \
    --description "Roadshow container images" \
    --project "$PROJECT_ID" >/dev/null
else
  log "Artifact Registry repository ${ARTIFACT_REPOSITORY} exists."
fi

if ! gcloud secrets describe "$API_TOKEN_SECRET" --project "$PROJECT_ID" >/dev/null 2>&1; then
  fail "Secret ${API_TOKEN_SECRET} does not exist. Create it first, for example: printf '%s' \"\$ROADSHOW_API_ACCESS_TOKEN\" | gcloud secrets create ${API_TOKEN_SECRET} --data-file=- --replication-policy=automatic --project ${PROJECT_ID}"
fi

ENABLED_SECRET_VERSION="$(gcloud secrets versions list "$API_TOKEN_SECRET" \
  --project "$PROJECT_ID" \
  --filter='state:ENABLED' \
  --limit=1 \
  --format='value(name)')"
if [[ -z "$ENABLED_SECRET_VERSION" ]]; then
  fail "Secret ${API_TOKEN_SECRET} exists but has no enabled versions."
fi
log "Secret ${API_TOKEN_SECRET} exists and has an enabled version."

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
if [[ -z "$RUNTIME_SERVICE_ACCOUNT" ]]; then
  EXISTING_FRONTEND_SA="$(gcloud run services describe "$FRONTEND_SERVICE" \
    --region "$REGION" \
    --project "$PROJECT_ID" \
    --format='value(spec.template.spec.serviceAccountName)' 2>/dev/null || true)"
  if [[ -n "$EXISTING_FRONTEND_SA" ]]; then
    RUNTIME_SERVICE_ACCOUNT="$EXISTING_FRONTEND_SA"
  else
    RUNTIME_SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
  fi
fi

log "Granting ${RUNTIME_SERVICE_ACCOUNT} access to ${API_TOKEN_SECRET}."
gcloud secrets add-iam-policy-binding "$API_TOKEN_SECRET" \
  --project "$PROJECT_ID" \
  --member "serviceAccount:${RUNTIME_SERVICE_ACCOUNT}" \
  --role roles/secretmanager.secretAccessor >/dev/null

BACKEND_URL="$(gcloud run services describe "$BACKEND_SERVICE" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --format='value(status.url)')"
if [[ -z "$BACKEND_URL" ]]; then
  fail "Backend service ${BACKEND_SERVICE} was not found in ${REGION}."
fi
log "Backend service found at ${BACKEND_URL}."

log "Submitting frontend build and deploy with image tag ${IMAGE_TAG}."
gcloud builds submit \
  --project "$PROJECT_ID" \
  --config cloudbuild.frontend.yaml \
  --substitutions "_REGION=${REGION},_SERVICE=${FRONTEND_SERVICE},_ARTIFACT_REPOSITORY=${ARTIFACT_REPOSITORY},_API_TOKEN_SECRET=${API_TOKEN_SECRET},_BACKEND_API_BASE_URL=${BACKEND_URL}/api,_IMAGE_TAG=${IMAGE_TAG}"

FRONTEND_URL="$(gcloud run services describe "$FRONTEND_SERVICE" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --format='value(status.url)')"
if [[ -z "$FRONTEND_URL" ]]; then
  fail "Frontend service ${FRONTEND_SERVICE} was not found after deploy."
fi

log "Updating backend CORS origin to ${FRONTEND_URL}."
gcloud run services update "$BACKEND_SERVICE" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --update-env-vars "ROADSHOW_CORS_ORIGINS=${FRONTEND_URL}" >/dev/null

log "Frontend deploy completed."
log "Application: ${FRONTEND_URL}"
log "Proxy health check: ${FRONTEND_URL}/api/roadshow/health"
log "Login page: ${FRONTEND_URL}/login"

if command -v curl >/dev/null 2>&1; then
  log "Checking frontend proxy health."
  curl -fsS "${FRONTEND_URL}/api/roadshow/health" >/dev/null \
    && log "Proxy health check succeeded." \
    || log "Proxy health check did not succeed yet. Cloud Run may still be warming up; retry the URL above."
fi
