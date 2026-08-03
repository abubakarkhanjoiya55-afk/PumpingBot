#!/bin/bash
# Convert / redeploy reasonable-essence as My Signals (not PumpingBot).
# RAILWAY_TOKEN must be the project token for reasonable-essence
# (same token that already can `railway up --service web`).

set -euo pipefail

SERVICE="${RAILWAY_MY_SIGNALS_SERVICE:-web}"

if [ -z "${RAILWAY_TOKEN:-}" ]; then
  echo "RAILWAY_TOKEN missing"
  exit 1
fi

echo "=== My Signals deploy ==="
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
  railway up --service "$svc" --detach -m "My Signals standalone (auto)"
}

if upload "$SERVICE"; then
  echo "Deploy triggered for service=$SERVICE"
elif upload my-signals; then
  echo "Deploy triggered for service=my-signals"
elif upload my_signals; then
  echo "Deploy triggered for service=my_signals"
else
  echo "::error::Could not railway up to web/my-signals"
  exit 1
fi

set +e
railway variable set --service "$SERVICE" --skip-deploys \
  NTFY_TOPIC=pumpingbot-signals \
  PORT=8000 2>/dev/null \
  || railway variable set --service my-signals --skip-deploys \
       NTFY_TOPIC=pumpingbot-signals PORT=8000 2>/dev/null \
  || echo "::warning::Could not set My Signals variables"
set -e

echo "Done. Confirm shortly:"
echo "  https://web-production-26ef9.up.railway.app/api  → My Signals API"
echo "  (or the my-signals service domain if web was not the target)"
