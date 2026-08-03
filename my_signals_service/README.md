# My Signals — standalone Railway service

PumpingBot se **alag** deploy. Sirf crypto alert PWA + scanner.

## Railway pe naya service (ek dafa)

1. Railway project `reasonable-essence` kholo  
2. **+ New** → **GitHub Repo** (same `PumpingBot` repo) **ya** Empty service  
3. Service name: **`my-signals`**  
4. Settings:
   - **Root Directory:** `/` (repo root)
   - **Dockerfile path:** `my_signals_service/Dockerfile`
   - ya Config-as-code: `my_signals_service/railway.toml`
5. Variables (optional):
   ```
   MY_SIGNALS_PREFIX=
   NTFY_TOPIC=pumpingbot-signals
   PORT=8000
   ```
6. Deploy → public URL milegi, e.g.  
   `https://my-signals-production-xxxx.up.railway.app`

## PumpingBot (`web`) pe ye variables

```
EMBED_MY_SIGNALS=0
MY_SIGNALS_URL=https://my-signals-production-xxxx.up.railway.app
```

Iske baad:
- `web-production-.../my-signals/` → My Signals service pe redirect  
- PumpingBot sirf trading/bot  
- My Signals alag online/restart

## Local test

```bash
cd /path/to/PumpingBot
pip install -r my_signals_service/requirements.txt
MY_SIGNALS_PREFIX= uvicorn my_signals_service.app:app --reload --port 8010
# open http://127.0.0.1:8010/
```

## Health

`GET /api` → `{ "message": "My Signals API", "embedded_in_pumpingbot": false }`
