#!/usr/bin/env bash
# Auto Scene Cutter — easy local start (Mac/Linux)
set -e
cd "$(dirname "$0")"

echo "Dependencies install ho rahi hain..."
python3 -m pip install -r requirements.txt

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "WARNING: ffmpeg nahi mila."
  echo "Ubuntu/Debian: sudo apt install ffmpeg"
  echo "Mac: brew install ffmpeg"
fi

PORT="${PORT:-5000}"
echo ""
echo "Server start ho raha hai..."
echo "Browser mein yeh kholo: http://127.0.0.1:${PORT}"
echo "Band karne ke liye: Ctrl+C"
echo ""
python3 -c "from app import app; app.run(host='127.0.0.1', port=${PORT}, debug=False)"
