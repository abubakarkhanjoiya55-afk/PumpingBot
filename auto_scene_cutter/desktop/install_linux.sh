#!/usr/bin/env bash
# SceneCut Pro+ — Linux desktop entry installer
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/SceneCutProPlus"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/256x256/apps"

echo "Installing SceneCut Pro+ → $APP_DIR"
mkdir -p "$APP_DIR" "$DESKTOP_DIR" "$ICON_DIR"
rsync -a --delete \
  --exclude '.git' --exclude '__pycache__' --exclude '.venv' \
  --exclude 'output' --exclude '_uploads' --exclude 'dist' --exclude 'build' \
  "$ROOT/" "$APP_DIR/"

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

# Simple PNG icon from existing brand isn't available — skip if none
ENTRY="$DESKTOP_DIR/scenecut-pro-plus.desktop"
cat > "$ENTRY" <<EOF
[Desktop Entry]
Type=Application
Name=SceneCut Pro+
Comment=AI Movie Scene Cutter
Exec=$APP_DIR/.venv/bin/python $APP_DIR/desktop_app.py
Path=$APP_DIR
Terminal=false
Categories=AudioVideo;Video;
StartupNotify=true
EOF
chmod +x "$ENTRY"

# User desktop shortcut if available
if [ -d "$HOME/Desktop" ]; then
  cp "$ENTRY" "$HOME/Desktop/SceneCut Pro+.desktop"
  chmod +x "$HOME/Desktop/SceneCut Pro+.desktop"
fi

echo "Done. Launch from app menu: SceneCut Pro+"
echo "Or: $APP_DIR/.venv/bin/python $APP_DIR/desktop_app.py"
