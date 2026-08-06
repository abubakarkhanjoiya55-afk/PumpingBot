# Cloud agent notes

## Local / cloud apps

After `bash scripts/dev-install.sh`, these services are available:

| App | URL | Health check |
|-----|-----|--------------|
| PumpingBot | http://127.0.0.1:8000 | `GET /api` → `"PumpingBot Smart API"` |
| My Signals | http://127.0.0.1:8010 | `GET /api` → `"My Signals API"` |
| Voltix | http://127.0.0.1:8080 | `GET /api/health` |
| MEXC Alerter | http://127.0.0.1:3847 | open dashboard HTML |

## Commands

```bash
source .venv/bin/activate
TRADING_BACKEND=agent USE_METAAPI=0 EMBED_MY_SIGNALS=0 uvicorn main:app --host 0.0.0.0 --port 8000
MY_SIGNALS_PREFIX= uvicorn my_signals_service.app:app --host 0.0.0.0 --port 8010
cd voltix/server && PORT=8080 uvicorn main:app --host 0.0.0.0 --port 8080
cd mexc-breakout-alerter && node src/index.js
```

MT5 / Windows VPS pieces (`local_agent`, `vps_supervisor`) need Windows + MetaTrader and are not started in cloud Linux VMs.
