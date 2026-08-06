#!/usr/bin/env bash
# Lightweight start hook — terminals launch the actual app processes.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -d .venv ]]; then
  echo "[dev-start] Missing .venv — run scripts/dev-install.sh first"
  exit 1
fi

# Ensure .env for mexc alerter exists
if [[ -f mexc-breakout-alerter/.env.example && ! -f mexc-breakout-alerter/.env ]]; then
  cp mexc-breakout-alerter/.env.example mexc-breakout-alerter/.env
fi

# Ensure frontend builds exist (fast no-op if already built)
if [[ ! -f client/dist/index.html ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
  (cd client && npm run build)
fi
if [[ ! -f voltix/dist/index.html ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
  (cd voltix && npm run build)
fi

mkdir -p device_care/data voltix/server/data
echo "[dev-start] Ready — app terminals will serve :8000 :8010 :8080 :3847"
