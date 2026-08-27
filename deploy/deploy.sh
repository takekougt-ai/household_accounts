#!/usr/bin/env bash
# Provision BigQuery + deploy the Cloud Function + schedule it with Cloud Scheduler.
#
# Prerequisites:
#   - gcloud CLI authenticated (`gcloud auth login`) with an active project set
#   - APIs enabled: bigquery, cloudfunctions, cloudscheduler, cloudbuild, run
#   - Secrets available as env vars in your shell before running this script:
#       GEMINI_API_KEY, MONEYFORWARD_EMAIL, MONEYFORWARD_PASSWORD
#
# Usage:
#   PROJECT_ID=my-gcp-project REGION=asia-northeast1 ./deploy/deploy.sh

set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID}"
REGION="${REGION:-asia-northeast1}"
BQ_DATASET="${BQ_DATASET:-household_accounts}"
BQ_TABLE="${BQ_TABLE:-amex_transactions}"
FUNCTION_NAME="${FUNCTION_NAME:-sync-amex-transactions}"
SCHEDULER_JOB="${SCHEDULER_JOB:-sync-amex-transactions-daily}"

: "${GEMINI_API_KEY:?Set GEMINI_API_KEY}"
: "${MONEYFORWARD_EMAIL:?Set MONEYFORWARD_EMAIL}"
: "${MONEYFORWARD_PASSWORD:?Set MONEYFORWARD_PASSWORD}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Enabling required APIs"
gcloud services enable \
  bigquery.googleapis.com \
  cloudfunctions.googleapis.com \
  cloudscheduler.googleapis.com \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  --project "$PROJECT_ID"

echo "==> Creating BigQuery dataset/table (idempotent)"
bq --project_id="$PROJECT_ID" query --use_legacy_sql=false < "$REPO_ROOT/sql/create_tables.sql"

echo "==> Deploying Cloud Function (Gen2, HTTP trigger)"
gcloud functions deploy "$FUNCTION_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --gen2 \
  --runtime python312 \
  --source "$REPO_ROOT/scripts" \
  --entry-point sync_amex_transactions \
  --trigger-http \
  --no-allow-unauthenticated \
  --memory 256Mi \
  --timeout 300s \
  --set-env-vars "GCP_PROJECT_ID=$PROJECT_ID,BQ_DATASET=$BQ_DATASET,BQ_TABLE=$BQ_TABLE" \
  --set-env-vars "GEMINI_API_KEY=$GEMINI_API_KEY,MONEYFORWARD_EMAIL=$MONEYFORWARD_EMAIL,MONEYFORWARD_PASSWORD=$MONEYFORWARD_PASSWORD"

FUNCTION_URL=$(gcloud functions describe "$FUNCTION_NAME" \
  --project "$PROJECT_ID" --region "$REGION" --gen2 \
  --format="value(serviceConfig.uri)")

echo "==> Creating a dedicated service account for Cloud Scheduler to invoke the function"
SCHEDULER_SA="scheduler-invoker@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud iam service-accounts create scheduler-invoker \
  --project "$PROJECT_ID" \
  --display-name "Cloud Scheduler -> Cloud Function invoker" 2>/dev/null || true

gcloud functions add-invoker-policy-binding "$FUNCTION_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --gen2 \
  --member "serviceAccount:${SCHEDULER_SA}"

echo "==> Creating/updating the daily Cloud Scheduler job"
if gcloud scheduler jobs describe "$SCHEDULER_JOB" --project "$PROJECT_ID" --location "$REGION" >/dev/null 2>&1; then
  gcloud scheduler jobs update http "$SCHEDULER_JOB" \
    --project "$PROJECT_ID" --location "$REGION" \
    --schedule "0 6 * * *" --time-zone "Asia/Tokyo" \
    --uri "$FUNCTION_URL" --http-method GET \
    --oidc-service-account-email "$SCHEDULER_SA"
else
  gcloud scheduler jobs create http "$SCHEDULER_JOB" \
    --project "$PROJECT_ID" --location "$REGION" \
    --schedule "0 6 * * *" --time-zone "Asia/Tokyo" \
    --uri "$FUNCTION_URL" --http-method GET \
    --oidc-service-account-email "$SCHEDULER_SA"
fi

echo "==> Done. Function URL: $FUNCTION_URL"
