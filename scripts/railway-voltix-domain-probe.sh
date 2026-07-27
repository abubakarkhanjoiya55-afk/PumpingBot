#!/bin/bash
set -euo pipefail
export RAILWAY_TOKEN
PROJECT_ID=c2f246da-a5ec-4432-ad4e-925438b85982
SERVICE_ID=ccf2b3d6-82b2-43cc-801a-d573cc76b490
SERVICE_NAME=voltix
ENV_NAME=production

cd "$(dirname "$0")/../voltix"
set +e
railway link --project "$PROJECT_ID" --environment "$ENV_NAME" --service "$SERVICE_NAME" </dev/null
echo "=== try domain without project flag ==="
railway domain voltix.exchange --service "$SERVICE_NAME" --environment "$ENV_NAME" --json
echo "=== try domain www ==="
railway domain www.voltix.exchange --service "$SERVICE_NAME" --environment "$ENV_NAME" --json
echo "=== railway status ==="
railway status --json
echo "=== GraphQL customDomainCreate attempt ==="
# resolve env id via status json if possible
python3 - <<'PY'
import json,os,urllib.request,subprocess
token=os.environ['RAILWAY_TOKEN']
# try status
try:
  out=subprocess.check_output(['railway','status','--json'], text=True)
  print('status', out[:1000])
  st=json.loads(out)
except Exception as e:
  print('status failed', e); st={}

def gql(query):
  req=urllib.request.Request(
    'https://backboard.railway.com/graphql/v2',
    data=json.dumps({'query':query}).encode(),
    headers={'Content-Type':'application/json','Authorization':f'Bearer {token}'},
    method='POST',
  )
  with urllib.request.urlopen(req, timeout=30) as r:
    return json.loads(r.read())

# list projects
print('me', json.dumps(gql('{ me { id email } }'))[:500])
print('projects', json.dumps(gql('{ projects { edges { node { id name } } } }'))[:800])
pid='$PROJECT_ID'
q='''
query {
  project(id: "%s") {
    id
    name
    environments { edges { node { id name } } }
    services { edges { node { id name } } }
  }
}
''' % 'c2f246da-a5ec-4432-ad4e-925438b85982'
print('project', json.dumps(gql(q))[:1500])
PY
set -e
