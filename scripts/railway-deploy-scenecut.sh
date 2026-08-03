#!/bin/bash
# Deploy SceneCut Pro to Railway as a dedicated permanent service.
set -euo pipefail

PROJECT_ID="${RAILWAY_PROJECT_ID:-c2f246da-a5ec-4432-ad4e-925438b85982}"
SERVICE_NAME="${SCENECUT_RAILWAY_SERVICE:-scenecut}"
ENVIRONMENT_NAME="${RAILWAY_ENVIRONMENT:-production}"

if [ -z "${RAILWAY_TOKEN:-}" ]; then
  echo "RAILWAY_TOKEN missing"
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/auto_scene_cutter"
export RAILWAY_TOKEN

echo "=== SceneCut Pro Railway deploy ==="
echo "Project: $PROJECT_ID  Service: $SERVICE_NAME  Env: $ENVIRONMENT_NAME"

# Create service if it does not exist yet (best-effort)
set +e
railway link --project "$PROJECT_ID" --environment "$ENVIRONMENT_NAME" --service "$SERVICE_NAME" </dev/null
LINK_RC=$?
set -e
if [ "$LINK_RC" -ne 0 ]; then
  echo "Service '$SERVICE_NAME' missing — creating..."
  set +e
  railway add --service "$SERVICE_NAME" --project "$PROJECT_ID" --environment "$ENVIRONMENT_NAME" 2>&1 || \
    railway service create "$SERVICE_NAME" 2>&1 || true
  railway link --project "$PROJECT_ID" --environment "$ENVIRONMENT_NAME" --service "$SERVICE_NAME" </dev/null
  set -e
fi

echo "Uploading SceneCut from $(pwd) ..."
railway up --service "$SERVICE_NAME" --detach -m "scenecut deploy $(date -u +%Y%m%d%H%M%S)"
echo "railway up OK"

echo "Generating / fetching public domain ..."
set +e
DOMAIN_OUT="$(railway domain --service "$SERVICE_NAME" --project "$PROJECT_ID" --environment "$ENVIRONMENT_NAME" --json 2>&1)"
echo "domain json: $DOMAIN_OUT"
if ! printf '%s' "$DOMAIN_OUT" | grep -Eq 'railway\.app|\{'; then
  DOMAIN_OUT="$(railway domain --service "$SERVICE_NAME" --environment "$ENVIRONMENT_NAME" --json 2>&1)"
  echo "domain json (linked): $DOMAIN_OUT"
fi
if ! printf '%s' "$DOMAIN_OUT" | grep -Eq 'railway\.app|\{'; then
  DOMAIN_OUT="$(railway domain --service "$SERVICE_NAME" --environment "$ENVIRONMENT_NAME" 2>&1)"
  echo "domain plain: $DOMAIN_OUT"
fi
set -e

PUBLIC_HOST="$(printf '%s\n' "$DOMAIN_OUT" | grep -Eo '[a-zA-Z0-9][a-zA-Z0-9.-]*\.up\.railway\.app' | head -1 || true)"
if [ -z "$PUBLIC_HOST" ]; then
  PUBLIC_HOST="$(printf '%s\n' "$DOMAIN_OUT" | python3 -c '
import sys,json,re
raw=sys.stdin.read().strip()
try:
  data=json.loads(raw)
except Exception:
  m=re.search(r"[a-zA-Z0-9.-]+\.up\.railway\.app", raw)
  print(m.group(0) if m else "")
  raise SystemExit
def walk(x):
  if isinstance(x,str):
    if ".up.railway.app" in x:
      print(x.replace("https://","").replace("http://","").split("/")[0]); raise SystemExit
  elif isinstance(x,dict):
    for v in x.values(): walk(v)
  elif isinstance(x,list):
    for v in x: walk(v)
walk(data)
' 2>/dev/null || true)"
fi

if [ -z "$PUBLIC_HOST" ]; then
  echo "Could not obtain Railway domain automatically."
  echo "Manual: Railway → service scenecut → Settings → Networking → Generate Domain"
  exit 0
fi

PUBLIC_URL="https://${PUBLIC_HOST}"
echo "PUBLIC_URL=$PUBLIC_URL"

if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  echo "### SceneCut Pro permanent URL" >> "$GITHUB_STEP_SUMMARY"
  echo "$PUBLIC_URL" >> "$GITHUB_STEP_SUMMARY"
  echo "Download: ${PUBLIC_URL}/download" >> "$GITHUB_STEP_SUMMARY"
fi

echo "Waiting for health at $PUBLIC_URL/health ..."
for i in $(seq 1 90); do
  code="$(curl -s -o /tmp/scenecut_health.json -w '%{http_code}' --max-time 12 "$PUBLIC_URL/health" || true)"
  body="$(cat /tmp/scenecut_health.json 2>/dev/null || true)"
  echo "  try $i: HTTP $code $body"
  if [ "$code" = "200" ]; then
    echo "Healthy permanent URL: $PUBLIC_URL"
    echo "Download page: $PUBLIC_URL/download"
    exit 0
  fi
  sleep 10
done

echo "Build may still be running. URL reserved: $PUBLIC_URL"
exit 0
