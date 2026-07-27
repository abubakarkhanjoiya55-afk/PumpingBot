#!/bin/bash
# Deploy Voltix (FastAPI + SPA) to Railway as a dedicated service.
set -euo pipefail

PROJECT_ID="${RAILWAY_PROJECT_ID:-c2f246da-a5ec-4432-ad4e-925438b85982}"
SERVICE_NAME="${VOLTIX_RAILWAY_SERVICE:-voltix}"

if [ -z "${RAILWAY_TOKEN:-}" ]; then
  echo "RAILWAY_TOKEN missing"
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/voltix"
export RAILWAY_TOKEN

echo "=== Voltix Railway deploy ==="
echo "Project: $PROJECT_ID  Service: $SERVICE_NAME"

set +e
railway link --project "$PROJECT_ID" </dev/null
railway service "$SERVICE_NAME" </dev/null
set -e

echo "Uploading Voltix from $(pwd) ..."
railway up --service "$SERVICE_NAME" --detach -m "voltix deploy $(date -u +%Y%m%d%H%M%S)"
echo "railway up OK"

echo "Generating / fetching public domain ..."
set +e
DOMAIN_OUT="$(railway domain --service "$SERVICE_NAME" --project "$PROJECT_ID" --json 2>&1)"
echo "domain json: $DOMAIN_OUT"
if [ -z "$DOMAIN_OUT" ] || echo "$DOMAIN_OUT" | grep -qi 'error\|usage\|failed'; then
  DOMAIN_OUT="$(railway domain --service "$SERVICE_NAME" --project "$PROJECT_ID" 2>&1)"
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
    if ".up.railway.app" in x: print(x.replace("https://","").replace("http://","").split("/")[0]); raise SystemExit
  elif isinstance(x,dict):
    for v in x.values(): walk(v)
  elif isinstance(x,list):
    for v in x: walk(v)
walk(data)
' 2>/dev/null || true)"
fi

if [ -z "$PUBLIC_HOST" ]; then
  echo "Could not obtain Railway domain automatically."
  echo "Manual: Railway → service voltix → Settings → Networking → Generate Domain"
  exit 0
fi

PUBLIC_URL="https://${PUBLIC_HOST}"
echo "PUBLIC_URL=$PUBLIC_URL"
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  echo "### Voltix permanent URL" >> "$GITHUB_STEP_SUMMARY"
  echo "$PUBLIC_URL" >> "$GITHUB_STEP_SUMMARY"
fi

echo "Waiting for health at $PUBLIC_URL/api/health ..."
for i in $(seq 1 90); do
  code="$(curl -s -o /tmp/voltix_health.json -w '%{http_code}' --max-time 12 "$PUBLIC_URL/api/health" || true)"
  body="$(cat /tmp/voltix_health.json 2>/dev/null || true)"
  echo "  try $i: HTTP $code $body"
  if [ "$code" = "200" ]; then
    echo "Healthy permanent URL: $PUBLIC_URL"
    exit 0
  fi
  sleep 10
done

echo "Build may still be running. URL reserved: $PUBLIC_URL"
exit 0
