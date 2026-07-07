#!/bin/bash
# Deploy PumpingBot to Railway from CI or local shell.
# Required: RAILWAY_TOKEN (Account token from railway.app/account/tokens → No Team)
# Optional: RAILWAY_SERVICE_ID, RAILWAY_PROJECT_ID, RAILWAY_ENVIRONMENT_ID

set -euo pipefail

API="https://backboard.railway.com/graphql/v2"
PROJECT_ID="${RAILWAY_PROJECT_ID:-c2f246da-a5ec-4432-ad4e-925438b85982}"
SERVICE_ID="${RAILWAY_SERVICE_ID:-}"
ENV_ID="${RAILWAY_ENVIRONMENT_ID:-}"

if [ -z "${RAILWAY_TOKEN:-}" ]; then
  echo "RAILWAY_TOKEN missing"
  exit 1
fi

gql() {
  curl -sS -X POST "$API" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $RAILWAY_TOKEN" \
    -d "$1"
}

echo "=== Railway deploy ==="

try_railway_up() {
  echo "Trying railway up (uploads repo code directly) ..."
  railway up --project "$PROJECT_ID" --detach 2>&1 && return 0
  railway up --detach 2>&1 && return 0
  return 1
}

# Resolve service + environment IDs when only project ID is known
if [ -z "$SERVICE_ID" ] || [ -z "$ENV_ID" ]; then
  echo "Looking up services in project $PROJECT_ID ..."
  LOOKUP=$(gql "{\"query\":\"query { project(id: \\\"$PROJECT_ID\\\") { id name environments { edges { node { id name } } } services { edges { node { id name } } } } }\"}")
  if echo "$LOOKUP" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(1 if d.get('errors') else 0)" 2>/dev/null; then
    echo "$LOOKUP" | python3 -c "
import json, sys
data = json.load(sys.stdin)
proj = data['data']['project']
print('Project:', proj.get('name'), proj.get('id'))
services = [e['node'] for e in proj.get('services', {}).get('edges', [])]
envs = [e['node'] for e in proj.get('environments', {}).get('edges', [])]
for s in services:
    print('  Service:', s['name'], s['id'])
for e in envs:
    print('  Environment:', e['name'], e['id'])
pick = services[0]
for s in services:
    if s['name'].lower() in ('web', 'pumpingbot', 'backend', 'api'):
        pick = s
        break
env = envs[0]
open('/tmp/railway_ids.env', 'w').write(f\"SERVICE_ID={pick['id']}\\nENV_ID={env['id']}\\n\")
print('Selected service:', pick['name'], pick['id'])
print('Selected environment:', env['name'], env['id'])
"
    # shellcheck disable=SC1091
    source /tmp/railway_ids.env
  else
    echo "$LOOKUP" | python3 -m json.tool 2>/dev/null || echo "$LOOKUP"
    echo "::warning::GraphQL lookup failed (Not Authorized = wrong token type)"
    echo "Use Account token from https://railway.app/account/tokens (Team: No Team)"
    try_railway_up && exit 0
    echo "Deploy failed — update RAILWAY_TOKEN to Account token (not Project token)"
    exit 1
  fi
fi

if [ -z "$SERVICE_ID" ] || [ -z "$ENV_ID" ]; then
  echo "Could not resolve service/environment IDs"
  exit 1
fi

echo "Deploying service=$SERVICE_ID environment=$ENV_ID ..."

# Prefer GitHub latest commit deploy (works when Railway source is connected)
RESP=$(gql "{\"query\":\"mutation(\$serviceId: String!, \$environmentId: String!) { serviceInstanceDeploy(serviceId: \$serviceId, environmentId: \$environmentId, latestCommit: true) }\",\"variables\":{\"serviceId\":\"$SERVICE_ID\",\"environmentId\":\"$ENV_ID\"}}")
echo "$RESP" | python3 -m json.tool

if echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if not d.get('errors') else 1)"; then
  echo "Railway deploy triggered from latest GitHub commit."
  exit 0
fi

echo "GraphQL deploy failed — trying railway up (uploads repo code) ..."
if command -v railway >/dev/null 2>&1; then
  railway up --service "$SERVICE_ID" --environment "$ENV_ID" --detach
  exit 0
fi

echo "All deploy methods failed."
echo "Tip: use Account token from https://railway.app/account/tokens (No Team), not Project token."
exit 1
