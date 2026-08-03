#!/bin/bash
# Convert / redeploy reasonable-essence `web` as My Signals (not PumpingBot).
# Uses RAILWAY_TOKEN (project or account). Default project = reasonable-essence.

set -euo pipefail

PROJECT_ID="${RAILWAY_PROJECT_ID:-c2f246da-a5ec-4432-ad4e-925438b85982}"
SERVICE="${RAILWAY_MY_SIGNALS_SERVICE:-web}"

if [ -z "${RAILWAY_TOKEN:-}" ]; then
  echo "RAILWAY_TOKEN missing"
  exit 1
fi

echo "=== My Signals deploy ==="
echo "project=$PROJECT_ID service=$SERVICE"

# railway up reads root railway.toml — temporarily use My Signals Dockerfile
cp railway.toml "/tmp/railway.toml.bot.bak.$$"
cp my_signals_service/railway.toml railway.toml
cleanup() {
  mv "/tmp/railway.toml.bot.bak.$$" railway.toml 2>/dev/null || true
}
trap cleanup EXIT

echo "Uploading with dockerfilePath=my_signals_service/Dockerfile ..."
if railway up \
  --project "$PROJECT_ID" \
  --service "$SERVICE" \
  --detach \
  -m "My Signals standalone (auto)"; then
  echo "Deploy triggered for service=$SERVICE"
else
  echo "Primary service '$SERVICE' failed — trying my-signals / my_signals"
  railway up --project "$PROJECT_ID" --service my-signals --detach -m "My Signals" \
    || railway up --project "$PROJECT_ID" --service my_signals --detach -m "My Signals" \
    || {
      echo "Creating service my-signals ..."
      railway add --service my-signals --json || true
      railway up --project "$PROJECT_ID" --service my-signals --detach -m "My Signals create"
    }
fi

# Best-effort env (skip if token can't set vars)
set +e
railway variable set \
  --project "$PROJECT_ID" \
  --service "$SERVICE" \
  --skip-deploys \
  MY_SIGNALS_PREFIX= \
  NTFY_TOPIC=pumpingbot-signals \
  PORT=8000 \
  EMBEDDED_IN_PUMPINGBOT=0 2>/dev/null \
  || railway variable set --service "$SERVICE" --skip-deploys \
       NTFY_TOPIC=pumpingbot-signals PORT=8000 2>/dev/null \
  || echo "::warning::Could not set My Signals variables (set in dashboard if needed)"
set -e

echo "Done. Confirm: https://web-production-26ef9.up.railway.app/api → My Signals API"
