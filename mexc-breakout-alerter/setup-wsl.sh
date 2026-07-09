#!/bin/bash
# MEXC Breakout Alerter — WSL one-shot setup
# Usage: curl -fsSL ... | bash   OR   bash setup-wsl.sh

set -euo pipefail

REPO="https://github.com/abubakarkhanjoiya55-afk/PumpingBot.git"
INSTALL_DIR="${MEXC_HOME:-$HOME/PumpingBot}"
APP_DIR="$INSTALL_DIR/mexc-breakout-alerter"

echo "=== MEXC 4H Breakout Alerter — WSL Setup ==="

# Node.js check
if ! command -v node >/dev/null 2>&1; then
  echo "[1/4] Node.js install ho raha hai..."
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
  sudo apt-get install -y nodejs
else
  echo "[1/4] Node.js OK: $(node -v)"
fi

# Git check
if ! command -v git >/dev/null 2>&1; then
  echo "[2/4] Git install..."
  sudo apt-get update && sudo apt-get install -y git
else
  echo "[2/4] Git OK"
fi

# Clone or update repo
if [ -d "$INSTALL_DIR/.git" ]; then
  echo "[3/4] Repo update: $INSTALL_DIR"
  git -C "$INSTALL_DIR" pull origin main || git -C "$INSTALL_DIR" pull
else
  echo "[3/4] Repo clone: $INSTALL_DIR"
  git clone --depth 1 "$REPO" "$INSTALL_DIR"
fi

if [ ! -d "$APP_DIR" ]; then
  echo "ERROR: mexc-breakout-alerter folder nahi mila. git pull main try karo."
  exit 1
fi

cd "$APP_DIR"

# .env
if [ ! -f .env ]; then
  cp .env.example .env
  echo "[4/4] .env created — Telegram ke liye edit karo: nano .env"
else
  echo "[4/4] .env already exists"
fi

# Kill old instance on same port
pkill -f "mexc-breakout-alerter/src/index.js" 2>/dev/null || true
pkill -f "node src/index.js" 2>/dev/null || true
sleep 1

echo ""
echo "=== Setup complete ==="
echo "Folder: $APP_DIR"
echo ""
echo "Start karo:"
echo "  cd $APP_DIR"
echo "  npm start"
echo ""
echo "Browser: http://localhost:3847"
echo ""

# Auto-start if --run flag
if [ "${1:-}" = "--run" ]; then
  echo "Starting server..."
  exec npm start
fi
