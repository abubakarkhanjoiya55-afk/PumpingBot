#!/bin/bash
# PumpingBot one-command deploy — tokens env mein set karo phir run karo:
#   export RAILWAY_TOKEN="..."
#   export VERCEL_TOKEN="..."
#   ./scripts/deploy.sh

set -e
API_URL="${VITE_API_URL:-https://web-production-6a35f.up.railway.app}"

echo "=== PumpingBot Deploy ==="

# ── Railway ──────────────────────────────────────────────────────────────────
if [ -n "$RAILWAY_TOKEN" ] && [ -n "$RAILWAY_SERVICE_ID" ]; then
  echo "[Railway] Triggering deploy..."
  curl -s -X POST https://backboard.railway.com/graphql/v2 \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $RAILWAY_TOKEN" \
    -d "{\"query\":\"mutation { serviceInstanceDeploy(serviceId: \\\"$RAILWAY_SERVICE_ID\\\") }\"}" \
    | python3 -m json.tool
  echo "[Railway] Deploy triggered. Wait 2-3 min then check: $API_URL"
else
  echo "[Railway] SKIP — set RAILWAY_TOKEN + RAILWAY_SERVICE_ID"
fi

# ── Vercel ───────────────────────────────────────────────────────────────────
if [ -n "$VERCEL_TOKEN" ]; then
  echo "[Vercel] Building and deploying client..."
  cd "$(dirname "$0")/../client"
  npm ci
  VITE_API_URL="$API_URL" npx vercel deploy --prod --yes --token="$VERCEL_TOKEN"
  echo "[Vercel] Deploy done."
elif [ -n "$VERCEL_DEPLOY_HOOK" ]; then
  echo "[Vercel] Triggering deploy hook..."
  curl -s -X POST "$VERCEL_DEPLOY_HOOK"
  echo "[Vercel] Hook triggered."
else
  echo "[Vercel] SKIP — set VERCEL_TOKEN or VERCEL_DEPLOY_HOOK"
fi

echo "=== Done ==="
