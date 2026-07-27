#!/bin/bash
# Deploy Voltix (FastAPI + SPA) to Railway as a dedicated service.
# Uses RAILWAY_TOKEN. Does NOT touch the PumpingBot "web" service.
set -euo pipefail

PROJECT_ID="${RAILWAY_PROJECT_ID:-c2f246da-a5ec-4432-ad4e-925438b85982}"
SERVICE_NAME="${VOLTIX_RAILWAY_SERVICE:-voltix}"

if [ -z "${RAILWAY_TOKEN:-}" ]; then
  echo "RAILWAY_TOKEN missing"
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/voltix"

echo "=== Voltix Railway deploy ==="
echo "Project: $PROJECT_ID"
echo "Service: $SERVICE_NAME"

# Prefer linking to project + named service, then upload this folder as context.
export RAILWAY_TOKEN

set +e
railway link --project "$PROJECT_ID" 2>/dev/null
railway service "$SERVICE_NAME" 2>/dev/null || railway add --service "$SERVICE_NAME" 2>/dev/null
# Some CLI versions use different create syntax:
railway service create "$SERVICE_NAME" 2>/dev/null
set -e

echo "Uploading Voltix from $(pwd) ..."
if railway up --service "$SERVICE_NAME" --detach -m "voltix deploy $(date -u +%Y%m%d%H%M%S)"; then
  echo "railway up OK for service=$SERVICE_NAME"
else
  echo "Named service failed — trying service name variants..."
  for svc in voltix Voltix VOLTIX; do
    if railway up --service "$svc" --detach; then
      echo "railway up OK for service=$svc"
      exit 0
    fi
  done
  echo "Deploy failed"
  exit 1
fi

echo "Done. Attach custom domain voltix.exchange to this Railway service in the dashboard."
