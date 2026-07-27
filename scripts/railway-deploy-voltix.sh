#!/bin/bash
# Deploy Voltix (FastAPI + SPA) to Railway as a dedicated service.
# Uses RAILWAY_TOKEN. Does NOT touch the PumpingBot "web" service.
set -euo pipefail

PROJECT_ID="${RAILWAY_PROJECT_ID:-c2f246da-a5ec-4432-ad4e-925438b85982}"
SERVICE_NAME="${VOLTIX_RAILWAY_SERVICE:-voltix}"

if [ -z "${RAILWAY_TOKEN:-}" ]; then
  echo "RAILWAY_TOKEN missing"
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/voltix"

echo "=== Voltix Railway deploy ==="
echo "Project: $PROJECT_ID"
echo "Service: $SERVICE_NAME"

export RAILWAY_TOKEN

set +e
railway link --project "$PROJECT_ID" 2>/dev/null
railway service "$SERVICE_NAME" 2>/dev/null
railway add --service "$SERVICE_NAME" 2>/dev/null
railway service create "$SERVICE_NAME" 2>/dev/null
set -e

echo "Uploading Voltix from $(pwd) ..."
railway up --service "$SERVICE_NAME" --detach -m "voltix deploy $(date -u +%Y%m%d%H%M%S)"
echo "railway up OK for service=$SERVICE_NAME"

echo "Ensuring public Railway domain ..."
DOMAIN_JSON="$(railway domain --service "$SERVICE_NAME" --project "$PROJECT_ID" --json 2>/dev/null || true)"
echo "$DOMAIN_JSON"

# Parse domain from JSON if present; also try plain command output
PUBLIC_URL=""
if [ -n "$DOMAIN_JSON" ]; then
  PUBLIC_URL="$(python3 - <<'PY' "$DOMAIN_JSON"
import json,sys
raw=sys.argv[1] if len(sys.argv)>1 else ""
try:
    data=json.loads(raw)
except Exception:
    print(""); raise SystemExit
# shapes vary: {domain}, {domains:[]}, string
if isinstance(data, str):
    print(data); raise SystemExit
if isinstance(data, dict):
    for k in ("domain","url","hostname"):
        if data.get(k):
            print(data[k]); raise SystemExit
    doms=data.get("domains") or data.get("domainNames") or []
    if doms:
        d=doms[0]
        print(d.get("domain") if isinstance(d, dict) else d); raise SystemExit
print("")
PY
)" || true
fi

if [ -z "$PUBLIC_URL" ]; then
  # Fallback: non-json output
  PUBLIC_URL="$(railway domain --service "$SERVICE_NAME" --project "$PROJECT_ID" 2>/dev/null | rg -o '[a-zA-Z0-9.-]+\.up\.railway\.app' | head -1 || true)"
fi

if [ -n "$PUBLIC_URL" ]; then
  case "$PUBLIC_URL" in
    http*) ;;
    *) PUBLIC_URL="https://$PUBLIC_URL" ;;
  esac
  echo "PUBLIC_URL=$PUBLIC_URL"
  echo "PUBLIC_URL=$PUBLIC_URL" >> "$GITHUB_ENV" 2>/dev/null || true
  echo "### Voltix permanent URL" >> "${GITHUB_STEP_SUMMARY:-/dev/null}" 2>/dev/null || true
  echo "$PUBLIC_URL" >> "${GITHUB_STEP_SUMMARY:-/dev/null}" 2>/dev/null || true

  echo "Waiting for health ..."
  for i in $(seq 1 60); do
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$PUBLIC_URL/api/health" || true)"
    echo "  try $i: $code"
    if [ "$code" = "200" ]; then
      echo "Healthy: $PUBLIC_URL"
      exit 0
    fi
    sleep 10
  done
  echo "Deployed but health not green yet — open $PUBLIC_URL shortly"
else
  echo "Domain not parsed. Open Railway dashboard → service $SERVICE_NAME → Networking → Generate domain"
fi
