#!/usr/bin/env bash
# Production web entry (Railway / Docker)
set -euo pipefail
cd "$(dirname "$0")"

export PYTHONUNBUFFERED=1
export SCENECUT_WEB=1
PORT="${PORT:-8080}"

# Writable dirs for uploads / exports
mkdir -p _uploads output projects releases

# Rebuild student pack if missing (e.g. volume wipe)
if [ ! -f releases/SceneCut-Pro-Student.zip ]; then
  echo "Building student pack..."
  ./desktop/build_student_pack.sh || true
fi

echo "SceneCut Pro live on 0.0.0.0:${PORT}"
exec python3 - <<PY
import os
from waitress import serve
from app import app, _ensure_dirs

_ensure_dirs()
port = int(os.environ.get("PORT", "8080"))
serve(app, host="0.0.0.0", port=port, threads=8)
PY
