#!/bin/bash
# Deploy Voltix (FastAPI + SPA) to Railway as a dedicated service.
set -euo pipefail

PROJECT_ID="${RAILWAY_PROJECT_ID:-c2f246da-a5ec-4432-ad4e-925438b85982}"
SERVICE_NAME="${VOLTIX_RAILWAY_SERVICE:-voltix}"
ENVIRONMENT_NAME="${RAILWAY_ENVIRONMENT:-production}"

if [ -z "${RAILWAY_TOKEN:-}" ]; then
  echo "RAILWAY_TOKEN missing"
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/voltix"
export RAILWAY_TOKEN

echo "=== Voltix Railway deploy ==="
echo "Project: $PROJECT_ID  Service: $SERVICE_NAME  Env: $ENVIRONMENT_NAME"

set +e
railway link --project "$PROJECT_ID" --environment "$ENVIRONMENT_NAME" --service "$SERVICE_NAME" </dev/null
set -e

echo "Uploading Voltix from $(pwd) ..."
railway up --service "$SERVICE_NAME" --detach -m "voltix deploy $(date -u +%Y%m%d%H%M%S)"
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
  echo "Manual: Railway → service voltix → Settings → Networking → Generate Domain"
  exit 0
fi

PUBLIC_URL="https://${PUBLIC_HOST}"
echo "PUBLIC_URL=$PUBLIC_URL"

echo "Attaching custom domains voltix.exchange + www ..."
set +e
for host in voltix.exchange www.voltix.exchange; do
  echo "--- railway domain $host ---"
  CUST="$(railway domain "$host" --service "$SERVICE_NAME" --project "$PROJECT_ID" --environment "$ENVIRONMENT_NAME" --json 2>&1)"
  echo "$CUST"
  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    echo "### DNS for \`$host\`" >> "$GITHUB_STEP_SUMMARY"
    echo '```' >> "$GITHUB_STEP_SUMMARY"
    echo "$CUST" >> "$GITHUB_STEP_SUMMARY"
    echo '```' >> "$GITHUB_STEP_SUMMARY"
  fi
done
set -e

# Optional Spaceship DNS update (if secrets present in CI)
if [ -n "${SPACESHIP_API_KEY:-}" ] && [ -n "${SPACESHIP_API_SECRET:-}" ]; then
  echo "Updating Spaceship DNS for voltix.exchange → $PUBLIC_HOST"
  export PUBLIC_HOST
  python3 <<'PY'
import json, os, urllib.error, urllib.request

key = os.environ["SPACESHIP_API_KEY"]
secret = os.environ["SPACESHIP_API_SECRET"]
target = os.environ["PUBLIC_HOST"].removeprefix("https://").removeprefix("http://").split("/")[0]
headers = {
    "Content-Type": "application/json",
    "X-Api-Key": key,
    "X-Api-Secret": secret,
}

def call(method, url, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
        return r.status, body

base = "https://spaceship.dev/api/v1/dns/records/voltix.exchange"

# Fetch existing apex/www A/CNAME/ALIAS so we can delete conflicts
try:
    status, raw = call("GET", base + "?take=500&skip=0")
    print("GET", status, raw[:300])
    items = json.loads(raw).get("items") or []
except Exception as e:
    print("GET failed", e)
    items = []

to_delete = []
for rec in items:
    name = str(rec.get("name") or "")
    typ = str(rec.get("type") or "").upper()
    if name in ("@", "www") and typ in ("A", "AAAA", "CNAME", "ALIAS"):
        # Spaceship delete expects identifying fields
        d = {"type": typ, "name": name}
        for k in ("address", "cname", "alias", "value"):
            if rec.get(k) is not None:
                d[k] = rec[k]
        to_delete.append(d)

if to_delete:
    try:
        req = urllib.request.Request(
            base,
            data=json.dumps(to_delete).encode(),
            method="DELETE",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            print("DELETE", r.status, r.read()[:200])
    except Exception as e:
        print("DELETE failed", e)
        if hasattr(e, "read"):
            print(e.read()[:500])

# Prefer ALIAS for apex + CNAME for www (Spaceship-style)
put_items = [
    {"type": "ALIAS", "name": "@", "alias": target, "ttl": 60},
    {"type": "CNAME", "name": "www", "cname": target, "ttl": 60},
]
# Fallback shapes if API rejects field names
candidates = [
    put_items,
    [
        {"type": "CNAME", "name": "@", "cname": target, "ttl": 60},
        {"type": "CNAME", "name": "www", "cname": target, "ttl": 60},
    ],
    [
        {"type": "CNAME", "name": "@", "value": target, "ttl": 60},
        {"type": "CNAME", "name": "www", "value": target, "ttl": 60},
    ],
]

ok = False
for items in candidates:
    try:
        status, raw = call("PUT", base, {"force": True, "items": items})
        print("PUT", status, items, raw[:300])
        ok = True
        break
    except urllib.error.HTTPError as e:
        print("PUT failed", e.code, items, e.read()[:500])
    except Exception as e:
        print("PUT failed", e)

print("spaceship_ok", ok)
PY
else
  echo "No SPACESHIP_API_KEY/SECRET in env — set DNS at Spaceship:"
  echo "  ALIAS/CNAME @   → $PUBLIC_HOST"
  echo "  CNAME       www → $PUBLIC_HOST"
fi

if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  echo "### Voltix permanent URL" >> "$GITHUB_STEP_SUMMARY"
  echo "$PUBLIC_URL" >> "$GITHUB_STEP_SUMMARY"
  echo "### Desired custom domain" >> "$GITHUB_STEP_SUMMARY"
  echo "https://voltix.exchange" >> "$GITHUB_STEP_SUMMARY"
fi

echo "Waiting for health at $PUBLIC_URL/api/health ..."
for i in $(seq 1 90); do
  code="$(curl -s -o /tmp/voltix_health.json -w '%{http_code}' --max-time 12 "$PUBLIC_URL/api/health" || true)"
  body="$(cat /tmp/voltix_health.json 2>/dev/null || true)"
  echo "  try $i: HTTP $code $body"
  if [ "$code" = "200" ]; then
    echo "Healthy permanent URL: $PUBLIC_URL"
    # Also probe custom domain if DNS already switched
    for host in https://voltix.exchange https://www.voltix.exchange; do
      c="$(curl -s -o /dev/null -w '%{http_code}' --max-time 12 "$host/api/health" || true)"
      echo "  custom $host => $c"
    done
    exit 0
  fi
  sleep 10
done

echo "Build may still be running. URL reserved: $PUBLIC_URL"
exit 0
