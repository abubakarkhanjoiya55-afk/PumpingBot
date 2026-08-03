#!/bin/bash
# Deploy SceneCut Pro to Railway as a dedicated permanent service.
# Works with Account token (preferred) or Project token (GraphQL).
set -euo pipefail

API="https://backboard.railway.com/graphql/v2"
PROJECT_ID="${RAILWAY_PROJECT_ID:-c2f246da-a5ec-4432-ad4e-925438b85982}"
SERVICE_NAME="${SCENECUT_RAILWAY_SERVICE:-scenecut}"
ENVIRONMENT_NAME="${RAILWAY_ENVIRONMENT:-production}"
ENV_ID="${RAILWAY_ENVIRONMENT_ID:-48134280-3d02-49de-bd65-d8859a33627c}"
REPO_FULL="${SCENECUT_GITHUB_REPO:-abubakarkhanjoiya55-afk/PumpingBot}"
BRANCH="${SCENECUT_BRANCH:-main}"

if [ -z "${RAILWAY_TOKEN:-}" ]; then
  echo "RAILWAY_TOKEN missing"
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/auto_scene_cutter"
export RAILWAY_TOKEN

gql() {
  local body="$1"
  # Try Account/Bearer token first, then Project-Access-Token style
  local resp
  resp="$(curl -sS -X POST "$API" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $RAILWAY_TOKEN" \
    -d "$body" || true)"
  if printf '%s' "$resp" | grep -Eq '"errors"|Not Authorized|NotAuthorized|Unauthorized'; then
    resp="$(curl -sS -X POST "$API" \
      -H "Content-Type: application/json" \
      -H "Project-Access-Token: $RAILWAY_TOKEN" \
      -d "$body" || true)"
  fi
  printf '%s' "$resp"
}

echo "=== SceneCut Pro Railway deploy ==="
echo "Project: $PROJECT_ID  Service: $SERVICE_NAME  Env: $ENVIRONMENT_NAME"

echo "Looking up project services via GraphQL ..."
LOOKUP="$(gql "{\"query\":\"query { project(id: \\\"$PROJECT_ID\\\") { id name environments { edges { node { id name } } } services { edges { node { id name } } } } }\"}")"
echo "$LOOKUP" | python3 -m json.tool 2>/dev/null || echo "$LOOKUP"

SERVICE_ID="$(printf '%s' "$LOOKUP" | python3 -c '
import json,sys
raw=sys.stdin.read()
try:
  d=json.loads(raw)
except Exception:
  print(""); raise SystemExit
proj=(d.get("data") or {}).get("project") or {}
want="'"$SERVICE_NAME"'".lower()
for e in (proj.get("services") or {}).get("edges") or []:
  n=e.get("node") or {}
  if str(n.get("name","")).lower()==want:
    print(n.get("id","")); raise SystemExit
print("")
' 2>/dev/null || true)"

ENV_FROM_API="$(printf '%s' "$LOOKUP" | python3 -c '
import json,sys
raw=sys.stdin.read()
try:
  d=json.loads(raw)
except Exception:
  print(""); raise SystemExit
proj=(d.get("data") or {}).get("project") or {}
want="'"$ENVIRONMENT_NAME"'".lower()
envs=[(e.get("node") or {}) for e in (proj.get("environments") or {}).get("edges") or []]
for n in envs:
  if str(n.get("name","")).lower()==want:
    print(n.get("id","")); raise SystemExit
print(envs[0].get("id","") if envs else "")
' 2>/dev/null || true)"
if [ -n "$ENV_FROM_API" ]; then
  ENV_ID="$ENV_FROM_API"
fi

if [ -z "$SERVICE_ID" ]; then
  echo "Creating service '$SERVICE_NAME' ..."
  CREATE="$(gql "{\"query\":\"mutation(\$input: ServiceCreateInput!) { serviceCreate(input: \$input) { id name } }\",\"variables\":{\"input\":{\"projectId\":\"$PROJECT_ID\",\"name\":\"$SERVICE_NAME\"}}}")"
  echo "$CREATE" | python3 -m json.tool 2>/dev/null || echo "$CREATE"
  SERVICE_ID="$(printf '%s' "$CREATE" | python3 -c '
import json,sys
raw=sys.stdin.read()
try:
  d=json.loads(raw)
except Exception:
  print(""); raise SystemExit
print(((d.get("data") or {}).get("serviceCreate") or {}).get("id") or "")
' 2>/dev/null || true)"
fi

if [ -z "$SERVICE_ID" ]; then
  echo "::error::Could not create/find Railway service '$SERVICE_NAME'."
  echo "Sath setup (2 minutes):"
  echo "  1) https://railway.app → project open"
  echo "  2) New Service → Empty Service → name: scenecut"
  echo "  3) Settings → Root Directory = auto_scene_cutter"
  echo "  4) Settings → Builder = Dockerfile"
  echo "  5) Networking → Generate Domain"
  echo "  6) GitHub → Settings → Secrets → RAILWAY_TOKEN ="
  echo "     Account token from https://railway.app/account/tokens (Team: No Team)"
  exit 1
fi

echo "Service ID: $SERVICE_ID"
echo "Environment ID: $ENV_ID"

# Best-effort: point instance at this repo subdirectory + Dockerfile
echo "Configuring root directory / Dockerfile (best-effort) ..."
UPDATE="$(gql "{\"query\":\"mutation(\$serviceId: String!, \$environmentId: String!, \$input: ServiceInstanceUpdateInput!) { serviceInstanceUpdate(serviceId: \$serviceId, environmentId: \$environmentId, input: \$input) }\",\"variables\":{\"serviceId\":\"$SERVICE_ID\",\"environmentId\":\"$ENV_ID\",\"input\":{\"rootDirectory\":\"auto_scene_cutter\",\"dockerfilePath\":\"Dockerfile\"}}}")"
echo "$UPDATE" | python3 -m json.tool 2>/dev/null || echo "$UPDATE"

# Prefer uploading from this folder (works even before GitHub root-dir is set)
echo "Trying railway up from auto_scene_cutter/ ..."
set +e
railway link --project "$PROJECT_ID" --environment "$ENVIRONMENT_NAME" --service "$SERVICE_NAME" </dev/null
UP_OUT="$(railway up --service "$SERVICE_NAME" --detach -m "scenecut deploy $(date -u +%Y%m%d%H%M%S)" 2>&1)"
UP_RC=$?
echo "$UP_OUT"
set -e

if [ "$UP_RC" -ne 0 ]; then
  echo "railway up failed — trying GraphQL latestCommit deploy ..."
  DEPLOY="$(gql "{\"query\":\"mutation(\$serviceId: String!, \$environmentId: String!) { serviceInstanceDeploy(serviceId: \$serviceId, environmentId: \$environmentId, latestCommit: true) }\",\"variables\":{\"serviceId\":\"$SERVICE_ID\",\"environmentId\":\"$ENV_ID\"}}")"
  echo "$DEPLOY" | python3 -m json.tool 2>/dev/null || echo "$DEPLOY"
  if printf '%s' "$DEPLOY" | grep -Eq '"errors"|Not Authorized|Unauthorized'; then
    echo "::error::Railway token cannot deploy. Update GitHub secret RAILWAY_TOKEN to an Account token."
    echo "Then create empty service 'scenecut' once in Railway dashboard if needed."
    exit 1
  fi
fi

echo "Generating / fetching public domain ..."
set +e
DOMAIN_OUT="$(railway domain --service "$SERVICE_NAME" --project "$PROJECT_ID" --environment "$ENVIRONMENT_NAME" --json 2>&1)"
echo "domain json: $DOMAIN_OUT"
if ! printf '%s' "$DOMAIN_OUT" | grep -Eq 'railway\.app|\{'; then
  DOMAIN_OUT="$(railway domain --service "$SERVICE_NAME" --environment "$ENVIRONMENT_NAME" --json 2>&1)"
  echo "domain json (linked): $DOMAIN_OUT"
fi
# GraphQL domains fallback
if ! printf '%s' "$DOMAIN_OUT" | grep -Eq 'railway\.app'; then
  DOM_GQL="$(gql "{\"query\":\"query { domains(projectId: \\\"$PROJECT_ID\\\", environmentId: \\\"$ENV_ID\\\", serviceId: \\\"$SERVICE_ID\\\") { serviceDomains { domain } } }\"}")"
  echo "domains gql: $DOM_GQL"
  DOMAIN_OUT="$DOM_GQL"
fi
set -e

PUBLIC_HOST="$(printf '%s\n' "$DOMAIN_OUT" | grep -Eo '[a-zA-Z0-9][a-zA-Z0-9.-]*\.up\.railway\.app' | head -1 || true)"

if [ -z "$PUBLIC_HOST" ]; then
  echo "No domain yet — asking Railway CLI to create one ..."
  set +e
  GEN="$(railway domain --service "$SERVICE_NAME" --project "$PROJECT_ID" --environment "$ENVIRONMENT_NAME" 2>&1)"
  echo "$GEN"
  PUBLIC_HOST="$(printf '%s\n' "$GEN" | grep -Eo '[a-zA-Z0-9][a-zA-Z0-9.-]*\.up\.railway\.app' | head -1 || true)"
  set -e
fi

if [ -z "$PUBLIC_HOST" ]; then
  echo "Domain auto-create failed. Manual: Railway → scenecut → Networking → Generate Domain"
  echo "SERVICE_ID=$SERVICE_ID"
  exit 0
fi

PUBLIC_URL="https://${PUBLIC_HOST}"
echo "PUBLIC_URL=$PUBLIC_URL"

if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  {
    echo "### SceneCut Pro permanent URL"
    echo "$PUBLIC_URL"
    echo ""
    echo "| Page | Link |"
    echo "|---|---|"
    echo "| Editor | $PUBLIC_URL/ |"
    echo "| Download | $PUBLIC_URL/download |"
    echo "| Health | $PUBLIC_URL/health |"
  } >> "$GITHUB_STEP_SUMMARY"
fi

echo "Polling Railway deployment status ..."
for i in $(seq 1 120); do
  DEP_STATUS="$(gql "{\"query\":\"query { deployments(first: 3, input: { serviceId: \\\"$SERVICE_ID\\\", environmentId: \\\"$ENV_ID\\\" }) { edges { node { id status createdAt } } } }\"}")"
  echo "  deploy-status try $i: $DEP_STATUS" | head -c 500; echo
  STATUS="$(printf '%s' "$DEP_STATUS" | python3 -c '
import json,sys
raw=sys.stdin.read()
try:
  d=json.loads(raw)
except Exception:
  print(""); raise SystemExit
edges=((d.get("data") or {}).get("deployments") or {}).get("edges") or []
if not edges:
  print(""); raise SystemExit
print((edges[0].get("node") or {}).get("status") or "")
' 2>/dev/null || true)"
  echo "  latest deployment status=$STATUS"

  code="$(curl -s -o /tmp/scenecut_health.json -w '%{http_code}' --max-time 12 "$PUBLIC_URL/health" || true)"
  body="$(cat /tmp/scenecut_health.json 2>/dev/null || true)"
  echo "  health try $i: HTTP $code $body"
  if [ "$code" = "200" ]; then
    echo "Healthy permanent URL: $PUBLIC_URL"
    echo "Download page: $PUBLIC_URL/download"
    exit 0
  fi
  if printf '%s' "$STATUS" | grep -Eqi 'FAILED|CRASHED|REMOVED'; then
    echo "::error::Railway deployment $STATUS — open build logs in Railway dashboard for service scenecut"
    exit 1
  fi
  sleep 15
done

echo "Build may still be running. URL reserved: $PUBLIC_URL"
echo "Build logs (open in browser): https://railway.com/project/${PROJECT_ID}/service/${SERVICE_ID}"
exit 0
