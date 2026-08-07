#!/bin/bash
# Convert / redeploy reasonable-essence as My Signals (not PumpingBot).
# RAILWAY_TOKEN must be the project token for reasonable-essence
# (same token that already can `railway up --service web`).

set -euo pipefail

# Prefer dedicated my-signals service (created after trial). Fallback to web.
SERVICE="${RAILWAY_MY_SIGNALS_SERVICE:-my-signals}"

if [ -z "${RAILWAY_TOKEN:-}" ]; then
  echo "RAILWAY_TOKEN missing"
  exit 1
fi

echo "=== Crypto Pumping Signals deploy ==="
echo "service=$SERVICE (token-scoped project)"

# railway up reads root railway.toml — temporarily use My Signals Dockerfile
cp railway.toml "/tmp/railway.toml.bot.bak.$$"
cp my_signals_service/railway.toml railway.toml
cleanup() {
  mv "/tmp/railway.toml.bot.bak.$$" railway.toml 2>/dev/null || true
}
trap cleanup EXIT

# Do NOT pass --project: project tokens + CLI 5.x require --environment with --project.
# The existing GitHub RAILWAY_TOKEN already scopes to reasonable-essence (like prior deploys).
upload() {
  local svc="$1"
  echo "Uploading → service=$svc (dockerfilePath=my_signals_service/Dockerfile)"
  railway up --service "$svc" --detach -m "Crypto Pumping Signals v4.1 (auto)"
}

if upload "$SERVICE"; then
  echo "Deploy triggered for service=$SERVICE"
elif [ "$SERVICE" != "my-signals" ] && upload my-signals; then
  echo "Deploy triggered for service=my-signals"
elif upload web; then
  echo "Deploy triggered for service=web"
elif upload my_signals; then
  echo "Deploy triggered for service=my_signals"
else
  echo "::error::Could not railway up to my-signals/web"
  exit 1
fi

set +e
railway variable set --service my-signals --skip-deploys \
  MY_SIGNALS_PREFIX= \
  NTFY_TOPIC=pumpingbot-signals \
  PORT=8000 2>/dev/null \
  || railway variable set --service "$SERVICE" --skip-deploys \
       MY_SIGNALS_PREFIX= NTFY_TOPIC=pumpingbot-signals PORT=8000 2>/dev/null \
  || echo "::warning::Could not set My Signals variables"
set -e

echo "Done. Confirm shortly:"
echo "  Railway → my-signals → Networking domain /api"
echo "  Expect: Crypto Pumping Signals / My Signals API (not PumpingBot)"
