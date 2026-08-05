#!/usr/bin/env bash
# SceneCut Pro+ — one-click local start (Mac/Linux)
set -e
cd "$(dirname "$0")"

echo "▶ SceneCut Pro+"
echo "  Installing dependencies..."
python3 -m pip install -q -r requirements.txt

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "⚠  ffmpeg missing — install before cutting video:"
  echo "   Ubuntu/Debian: sudo apt install ffmpeg"
  echo "   Mac: brew install ffmpeg"
fi

PORT="${PORT:-5000}"
URL="http://127.0.0.1:${PORT}"
echo ""
echo "  Starting editor → ${URL}"
echo "  Stop with Ctrl+C"
echo ""

# Open browser shortly after bind (best-effort)
( sleep 1.2; python3 -m webbrowser "${URL}" >/dev/null 2>&1 || true ) &

python3 -c "from app import app; app.run(host='127.0.0.1', port=${PORT}, debug=False)"
