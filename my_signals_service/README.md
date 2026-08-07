# My Signals — standalone Railway service

PumpingBot se **alag** deploy. Sirf crypto alert PWA + scanner.

> Redeploy note: after Railway plan reactivation, service `my-signals` needs an active deployment (`scripts/railway-deploy-my-signals.sh`).

**Tumhara preferred layout:** [`../RAILWAY_PROJECTS.md`](../RAILWAY_PROJECTS.md)

| Project | App |
|---------|-----|
| `proactive-healing` | MT5 PumpingBot |
| `reasonable-essence` → service `web` | **My Signals** (Dockerfile switch) |

## `reasonable-essence` pe My Signals switch (recommended)

1. PR #47 merge → branch `main`  
2. Service **`web`** → Settings → Dockerfile path: **`my_signals_service/Dockerfile`**  
3. (Optional) rename service → `my-signals`  
4. Variables:
   ```
   MY_SIGNALS_PREFIX=
   NTFY_TOPIC=pumpingbot-signals
   PORT=8000
   ```
5. Redeploy → `/api` pe `"My Signals API"` aana chahiye

## `proactive-healing` (PumpingBot) variables

```
EMBED_MY_SIGNALS=0
MY_SIGNALS_URL=https://web-production-26ef9.up.railway.app
```
(URL wo jo My Signals deploy ke baad `/api` pe My Signals dikhaye)

## Local test

```bash
cd /path/to/PumpingBot
pip install -r my_signals_service/requirements.txt
MY_SIGNALS_PREFIX= uvicorn my_signals_service.app:app --reload --port 8010
# open http://127.0.0.1:8010/
```

## Health

`GET /api` → `{ "message": "My Signals API", "embedded_in_pumpingbot": false }`
