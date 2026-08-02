# PumpingBot Local MT5 Agent (No MetaAPI)

Fastest multi-user setup: each user runs this agent on **Windows** with their own MT5 terminal. The Railway server only broadcasts open/close commands over WebSocket.

## Why this is best
- **No MetaAPI bill**
- **Faster** — orders hit the broker from local MT5 (ms), not cloud RPC
- **Scales** — 10 or 1000 users; each brings their own MT5

## Master (you)
1. Install MT5 + login to your master account
2. `pip install -r local_agent/requirements.txt`
3. Set env and run:

```bat
set SERVER_URL=https://YOUR-RAILWAY-APP.up.railway.app
set USERNAME=admin
set PASSWORD=YourPassword
set MT5_LOGIN=12345678
set MT5_PASSWORD=YourMt5Pass
set MT5_SERVER=Exness-MT5Trial15
set AGENT_ROLE=master
set SYMBOLS=XAUUSDm,EURUSDm,GBPUSDm,BTCUSDm
python local_agent\agent.py
```

## Follower (each user)
Same steps, but:

```bat
set AGENT_ROLE=follower
set USERNAME=their_username
set PASSWORD=their_password
set MT5_LOGIN=...
set MT5_PASSWORD=...
set MT5_SERVER=...
python local_agent\agent.py
```

## Optional
- `MT5_PATH=C:\Program Files\MetaTrader 5\terminal64.exe` if multiple terminals
- `ACCESS_TOKEN=...` instead of USERNAME/PASSWORD

## Server flag
On Railway set:

```
TRADING_BACKEND=agent
USE_METAAPI=0
```

Dashboard → `/agents` shows who is online.
