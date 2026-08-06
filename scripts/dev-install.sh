#!/usr/bin/env bash
# Idempotent install for Cursor cloud agents / local setup.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[dev-install] Ensure python3-venv (Ubuntu/Debian)"
if ! python3 -m venv --help >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -qq
    sudo apt-get install -y -qq python3-venv python3.12-venv || sudo apt-get install -y -qq python3-venv
  fi
fi

echo "[dev-install] Python venv"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -r my_signals_service/requirements.txt
# voltix pins uvicorn>=0.32; keep root uvicorn==0.30 for PumpingBot compatibility
pip install 'fastapi>=0.115.0' 'pydantic>=2.0.0'

echo "[dev-install] Node packages"
if [[ -f client/package-lock.json ]]; then
  (cd client && npm ci)
else
  (cd client && npm install)
fi
if [[ -f voltix/package-lock.json ]]; then
  (cd voltix && npm ci)
else
  (cd voltix && npm install)
fi
# mexc-breakout-alerter has no npm deps beyond Node builtins; still ensure .env
if [[ -f mexc-breakout-alerter/.env.example && ! -f mexc-breakout-alerter/.env ]]; then
  cp mexc-breakout-alerter/.env.example mexc-breakout-alerter/.env
fi

echo "[dev-install] Frontend builds"
(cd client && npm run build)
(cd voltix && npm run build)

echo "[dev-install] Done"
