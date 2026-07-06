#!/bin/bash
# Railway environment variables — run with project token:
#   export RAILWAY_TOKEN="your-project-token"
#   ./scripts/railway-env.sh
#
# Service ID: c2f246da-a5ec-4432-ad4e-925438b85982

set -e
SERVICE_ID="${RAILWAY_SERVICE_ID:-c2f246da-a5ec-4432-ad4e-925438b85982}"

if [ -z "$RAILWAY_TOKEN" ]; then
  echo "Set RAILWAY_TOKEN first (Railway → Project → Settings → Tokens)"
  exit 1
fi

gql() {
  curl -s -X POST https://backboard.railway.com/graphql/v2 \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $RAILWAY_TOKEN" \
    -d "$1"
}

echo "Fetching environment for service $SERVICE_ID ..."
ENV_JSON=$(gql "{\"query\":\"query { service(id: \\\"$SERVICE_ID\\\") { id name project { id environments { edges { node { id name } } } } } }\"}")
echo "$ENV_JSON" | python3 -m json.tool 2>/dev/null || echo "$ENV_JSON"

# Required Railway variables (set manually in dashboard if this script can't):
cat <<'EOF'

── Set these in Railway → Service → Variables ──

PORT                  (auto-set by Railway)
DATABASE_URL          (add PostgreSQL plugin, then reference ${{Postgres.DATABASE_URL}})
METAAPI_TOKEN         (MetaApi JWT)
MASTER_ACCOUNT_ID     (default: 5e4d5291-3a52-4e73-9a95-2d6ea449843c)
SECRET_KEY            (random string for JWT)
EMAIL_USER            pumpingbot333@gmail.com
EMAIL_PASS            (Gmail app password)
ADMIN_EMAIL           pumpingbot333@gmail.com

── Build settings (railway.toml) ──
Builder: Dockerfile
Start: ./start.sh
Healthcheck: /

EOF
