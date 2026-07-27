#!/bin/bash
set -euo pipefail
PROJECT_ID="${RAILWAY_PROJECT_ID:-c2f246da-a5ec-4432-ad4e-925438b85982}"
SERVICE_NAME="${VOLTIX_RAILWAY_SERVICE:-voltix}"
ENVIRONMENT_NAME="${RAILWAY_ENVIRONMENT:-production}"
export RAILWAY_TOKEN

cd "$(dirname "$0")/../voltix"

echo "Linking..."
set +e
railway link --project "$PROJECT_ID" --environment "$ENVIRONMENT_NAME" --service "$SERVICE_NAME" </dev/null
set -e

for host in voltix.exchange www.voltix.exchange; do
  echo "=== Adding domain: $host ==="
  set +e
  OUT="$(railway domain "$host" --service "$SERVICE_NAME" --project "$PROJECT_ID" --environment "$ENVIRONMENT_NAME" --json 2>&1)"
  EC=$?
  set -e
  echo "exit=$EC"
  echo "$OUT"
  echo "$OUT" >> "${GITHUB_STEP_SUMMARY:-/dev/stdout}"
done

echo "=== Current domains (service) ==="
set +e
railway domain --service "$SERVICE_NAME" --project "$PROJECT_ID" --environment "$ENVIRONMENT_NAME" --json 2>&1
set -e
