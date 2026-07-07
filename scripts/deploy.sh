#!/bin/bash
# PumpingBot one-command deploy
#   export RAILWAY_TOKEN="..."   # Railway → Project → Settings → Tokens
#   ./scripts/deploy.sh

set -e
API_URL="${VITE_API_URL:-https://web-production-6a35f.up.railway.app}"
RAILWAY_SERVICE_ID="${RAILWAY_SERVICE_ID:-c2f246da-a5ec-4432-ad4e-925438b85982}"

echo "=== PumpingBot Deploy ==="

# ── Railway ──────────────────────────────────────────────────────────────────
if [ -n "$RAILWAY_TOKEN" ]; then
  echo "[Railway] Deploying service $RAILWAY_SERVICE_ID ..."
  if command -v railway >/dev/null 2>&1; then
    RAILWAY_TOKEN="$RAILWAY_TOKEN" railway up --service "$RAILWAY_SERVICE_ID" --detach || \
  else
    curl -s -X POST https://backboard.railway.com/graphql/v2 \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $RAILWAY_TOKEN" \
      -d "{\"query\":\"mutation { serviceInstanceDeploy(serviceId: \\\"$RAILWAY_SERVICE_ID\\\") }\"}" \
      | python3 -m json.tool
  fi
  echo "[Railway] Deploy triggered. Wait 2-3 min then check: $API_URL"
else
  echo "[Railway] SKIP — set RAILWAY_TOKEN (Project → Settings → Tokens)"
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
