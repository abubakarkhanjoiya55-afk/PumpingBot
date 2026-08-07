# My Signals — standalone Railway service

PumpingBot se **alag** deploy. Crypto alert PWA + scanner + login/subscription.

**Tumhara preferred layout:** [`../RAILWAY_PROJECTS.md`](../RAILWAY_PROJECTS.md)

| Project | App |
|---------|-----|
| `proactive-healing` | MT5 PumpingBot |
| `reasonable-essence` → service `web` | **My Signals** (Dockerfile switch) |

## `reasonable-essence` pe My Signals switch (recommended)

1. Service **`web`** → Settings → Dockerfile path: **`my_signals_service/Dockerfile`**
2. (Optional) rename service → `my-signals`
3. Variables:
   ```
   MY_SIGNALS_PREFIX=
   MY_SIGNALS_VERSION=4.1.4
   NTFY_TOPIC=pumpingbot-signals
   PORT=8000
   SECRET_KEY=<long-random>
   ADMIN99_PASSWORD=Goku.k.g99
   ADMIN_USDT_BEP20=0x906fdfced22b23f79e04415d6534386baf4f2e8e
   ```
4. Redeploy → `/api` pe `"Crypto Pumping Signals API"` + `"auth": true`

## `proactive-healing` (PumpingBot) variables

```
EMBED_MY_SIGNALS=0
MY_SIGNALS_URL=https://<your-my-signals-domain>
```

## Local test

```bash
cd /path/to/PumpingBot
pip install -r my_signals_service/requirements.txt
MY_SIGNALS_PREFIX= uvicorn my_signals_service.app:app --reload --port 8010
# open http://127.0.0.1:8010/
# Admin: Admin99 / Goku.k.g99  (URL: /?admin=1)
```

## Health

`GET /api` → `{ "message": "Crypto Pumping Signals API", "embedded_in_pumpingbot": false, "auth": true }`
