#!/bin/bash
# Attach voltix.exchange + www to Railway voltix service via GraphQL.
# Tries Project-Access-Token header (project tokens) AND Authorization Bearer (account tokens).
set -euo pipefail

PROJECT_ID="${RAILWAY_PROJECT_ID:-c2f246da-a5ec-4432-ad4e-925438b85982}"
SERVICE_ID="${VOLTIX_RAILWAY_SERVICE_ID:-ccf2b3d6-82b2-43cc-801a-d573cc76b490}"
ENV_ID="${RAILWAY_ENVIRONMENT_ID:-48134280-3d02-49de-bd65-d8859a33627c}"
SERVICE_NAME="${VOLTIX_RAILWAY_SERVICE:-voltix}"
ENVIRONMENT_NAME="${RAILWAY_ENVIRONMENT:-production}"

if [ -z "${RAILWAY_TOKEN:-}" ]; then
  echo "RAILWAY_TOKEN missing"
  exit 1
fi

export RAILWAY_TOKEN
cd "$(dirname "$0")/../voltix"

echo "=== CLI domain attempts ==="
set +e
railway link --project "$PROJECT_ID" --environment "$ENVIRONMENT_NAME" --service "$SERVICE_NAME" </dev/null
for host in voltix.exchange www.voltix.exchange; do
  echo "--- railway domain $host ---"
  railway domain "$host" --service "$SERVICE_NAME" --project "$PROJECT_ID" --environment "$ENVIRONMENT_NAME" --json 2>&1
done
set -e

echo "=== GraphQL customDomainCreate (Project-Access-Token + Bearer) ==="
python3 <<'PY'
import json, os, urllib.error, urllib.request

token = os.environ["RAILWAY_TOKEN"]
project_id = os.environ.get("RAILWAY_PROJECT_ID", "c2f246da-a5ec-4432-ad4e-925438b85982")
service_id = os.environ.get("VOLTIX_RAILWAY_SERVICE_ID", "ccf2b3d6-82b2-43cc-801a-d573cc76b490")
env_id = os.environ.get("RAILWAY_ENVIRONMENT_ID", "48134280-3d02-49de-bd65-d8859a33627c")

mutation = """
mutation customDomainCreate($input: CustomDomainCreateInput!) {
  customDomainCreate(input: $input) {
    id
    domain
    status {
      dnsRecords { host label purpose recordType requiredValue status currentValue }
      verificationToken
      verificationDnsHost
      certificateStatus
    }
  }
}
"""

query_domains = """
query {
  domains(projectId: "%s", environmentId: "%s", serviceId: "%s") {
    customDomains { id domain }
    serviceDomains { id domain }
  }
}
""" % (project_id, env_id, service_id)

def gql(headers, query, variables=None):
    body = {"query": query}
    if variables is not None:
        body["variables"] = variables
    req = urllib.request.Request(
        "https://backboard.railway.com/graphql/v2",
        data=json.dumps(body).encode(),
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            data = json.loads(raw)
        except Exception:
            data = {"raw": raw[:2000]}
        return e.code, data

auth_variants = [
    ("Project-Access-Token", {"Project-Access-Token": token}),
    ("Authorization Bearer", {"Authorization": f"Bearer {token}"}),
]

print("--- list domains ---")
for label, headers in auth_variants:
    code, data = gql(headers, query_domains)
    print(label, "status", code)
    print(json.dumps(data, indent=2)[:2500])

for host in ("voltix.exchange", "www.voltix.exchange"):
    print(f"--- create {host} ---")
    variables = {
        "input": {
            "projectId": project_id,
            "environmentId": env_id,
            "serviceId": service_id,
            "domain": host,
        }
    }
    # Some API versions also want targetPort
    variables_port = {
        "input": {
            "projectId": project_id,
            "environmentId": env_id,
            "serviceId": service_id,
            "domain": host,
            "targetPort": 8080,
        }
    }
    for label, headers in auth_variants:
        for name, vars_ in (("basic", variables), ("withPort", variables_port)):
            code, data = gql(headers, mutation, vars_)
            print(label, name, "HTTP", code)
            print(json.dumps(data, indent=2)[:3000])
            # Surface verification TXT if present
            try:
                st = data["data"]["customDomainCreate"]["status"]
                print("VERIFY_HOST", st.get("verificationDnsHost"))
                print("VERIFY_TOKEN", st.get("verificationToken"))
                print("DNS_RECORDS", st.get("dnsRecords"))
            except Exception:
                pass
PY

echo "=== Done ==="
