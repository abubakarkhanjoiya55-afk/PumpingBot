#!/bin/bash
# Deploy PumpingBot to proactive-healing (preferred) or set bot env vars.
# Does NOT deploy to reasonable-essence `web` (that service is My Signals).

set -euo pipefail

BOT_PROJECT="${RAILWAY_BOT_PROJECT_ID:-}"
BOT_SERVICE="${RAILWAY_BOT_SERVICE:-web}"
VPS_SECRET_VAL="${VPS_SECRET:-pumpingbot-vps-$(openssl rand -hex 8)}"
MY_SIGNALS_URL_VAL="${MY_SIGNALS_URL:-https://web-production-26ef9.up.railway.app}"

if [ -z "${RAILWAY_TOKEN:-}" ]; then
  echo "RAILWAY_TOKEN missing"
  exit 1
fi

echo "=== PumpingBot deploy ==="

deploy_ok=0

if [ -n "$BOT_PROJECT" ]; then
  echo "Deploying to RAILWAY_BOT_PROJECT_ID=$BOT_PROJECT service=$BOT_SERVICE"
  if railway up --project "$BOT_PROJECT" --service "$BOT_SERVICE" --detach -m "PumpingBot bot deploy"; then
    deploy_ok=1
  fi
  set +e
  railway variable set --project "$BOT_PROJECT" --service "$BOT_SERVICE" --skip-deploys \
    TRADING_BACKEND=agent \
    USE_METAAPI=0 \
    VPS_SECRET="$VPS_SECRET_VAL" \
    EMBED_MY_SIGNALS=0 \
    MY_SIGNALS_URL="$MY_SIGNALS_URL_VAL"
  set -e
else
  echo "::notice::RAILWAY_BOT_PROJECT_ID secret not set."
  echo "Bot code already auto-deploys on proactive-healing via GitHub if connected."
  echo "Trying GraphQL latestCommit deploy if SERVICE/ENV ids present..."
  if [ -n "${RAILWAY_SERVICE_ID:-}" ] && [ -n "${RAILWAY_ENVIRONMENT_ID:-}" ]; then
    chmod +x scripts/railway-deploy.sh
    # Old script targets shared project — only use when explicitly configured for BOT
    ./scripts/railway-deploy.sh && deploy_ok=1 || true
  fi
fi

if [ "$deploy_ok" -eq 0 ]; then
  echo "::notice::No direct bot upload. Verify https://web-production-c78a0.up.railway.app/api"
  echo "Set GitHub secret RAILWAY_BOT_PROJECT_ID = proactive-healing project UUID for CI deploys."
fi

echo "Required bot vars: TRADING_BACKEND=agent USE_METAAPI=0 VPS_SECRET=... EMBED_MY_SIGNALS=0"
echo "VPS_SECRET used this run (save for Windows VPS config.bat): $VPS_SECRET_VAL"
echo "Confirm bot: https://web-production-c78a0.up.railway.app/api → version 3.28.x"
