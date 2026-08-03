#!/bin/bash
# PumpingBot only (proactive-healing). Does NOT touch My Signals / reasonable-essence web.

set -euo pipefail

BOT_PROJECT="${RAILWAY_BOT_PROJECT_ID:-}"
BOT_SERVICE="${RAILWAY_BOT_SERVICE:-web}"
BOT_ENV="${RAILWAY_BOT_ENVIRONMENT:-production}"
VPS_SECRET_VAL="${VPS_SECRET:-pumpingbot-vps-live-2026}"

if [ -z "${RAILWAY_TOKEN:-}" ]; then
  echo "RAILWAY_TOKEN missing"
  exit 1
fi

echo "=== PumpingBot deploy (bot only) ==="

if [ -n "$BOT_PROJECT" ]; then
  echo "Uploading → project=$BOT_PROJECT service=$BOT_SERVICE env=$BOT_ENV"
  railway up \
    --project "$BOT_PROJECT" \
    --environment "$BOT_ENV" \
    --service "$BOT_SERVICE" \
    --detach \
    -m "PumpingBot go-live"
  set +e
  railway variable set \
    --project "$BOT_PROJECT" \
    --environment "$BOT_ENV" \
    --service "$BOT_SERVICE" \
    --skip-deploys \
    TRADING_BACKEND=agent \
    USE_METAAPI=0 \
    VPS_SECRET="$VPS_SECRET_VAL" \
    EMBED_MY_SIGNALS=0
  set -e
else
  echo "::notice::RAILWAY_BOT_PROJECT_ID not set — using GitHub auto-deploy on proactive-healing."
  echo "Code default VPS_SECRET=$VPS_SECRET_VAL (same value for Windows config.bat)"
fi

echo "Bot URL: https://web-production-c78a0.up.railway.app/api"
echo "Expect: version 3.28.x+, trading_backend=agent, use_metaapi=false"
