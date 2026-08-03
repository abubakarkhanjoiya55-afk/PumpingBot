#!/bin/bash
# Configure / deploy PumpingBot.
# IMPORTANT: do NOT railway-up onto reasonable-essence `web` (My Signals lives there).

set -euo pipefail

BOT_PROJECT="${RAILWAY_BOT_PROJECT_ID:-}"
BOT_SERVICE="${RAILWAY_BOT_SERVICE:-web}"
BOT_ENV="${RAILWAY_BOT_ENVIRONMENT:-production}"
VPS_SECRET_VAL="${VPS_SECRET:-pumpingbot-vps-$(openssl rand -hex 8)}"
MY_SIGNALS_URL_VAL="${MY_SIGNALS_URL:-https://web-production-26ef9.up.railway.app}"

if [ -z "${RAILWAY_TOKEN:-}" ]; then
  echo "RAILWAY_TOKEN missing"
  exit 1
fi

echo "=== PumpingBot deploy ==="

if [ -n "$BOT_PROJECT" ]; then
  echo "Deploying to RAILWAY_BOT_PROJECT_ID=$BOT_PROJECT service=$BOT_SERVICE env=$BOT_ENV"
  railway up \
    --project "$BOT_PROJECT" \
    --environment "$BOT_ENV" \
    --service "$BOT_SERVICE" \
    --detach \
    -m "PumpingBot bot deploy"
  set +e
  railway variable set \
    --project "$BOT_PROJECT" \
    --environment "$BOT_ENV" \
    --service "$BOT_SERVICE" \
    --skip-deploys \
    TRADING_BACKEND=agent \
    USE_METAAPI=0 \
    VPS_SECRET="$VPS_SECRET_VAL" \
    EMBED_MY_SIGNALS=0 \
    MY_SIGNALS_URL="$MY_SIGNALS_URL_VAL"
  set -e
  echo "VPS_SECRET for Windows config.bat: $VPS_SECRET_VAL"
else
  echo "::notice::RAILWAY_BOT_PROJECT_ID not set — skipping CI upload to proactive-healing."
  echo "Bot already on https://web-production-c78a0.up.railway.app (GitHub auto-deploy)."
  echo "Set dashboard vars on proactive-healing web:"
  echo "  TRADING_BACKEND=agent"
  echo "  USE_METAAPI=0"
  echo "  VPS_SECRET=<choose-secret>"
  echo "  EMBED_MY_SIGNALS=0"
  echo "  MY_SIGNALS_URL=$MY_SIGNALS_URL_VAL"
fi

echo "Confirm bot: https://web-production-c78a0.up.railway.app/api → version 3.28.x"
