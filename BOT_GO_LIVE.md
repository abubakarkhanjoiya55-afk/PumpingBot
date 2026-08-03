# PumpingBot go-live (`proactive-healing`)

## 1) Merge + deploy bot
1. Merge PR: https://github.com/abubakarkhanjoiya55-afk/PumpingBot/pull/47  
2. Railway project **`proactive-healing`** → service `web` → branch **`main`** → Redeploy  
3. Variables (`.env.bot.example` se):

```
TRADING_BACKEND=agent
USE_METAAPI=0
VPS_SECRET=apni-secret
EMBED_MY_SIGNALS=0
MY_SIGNALS_URL=https://<my-signals-url>
SECRET_KEY=...
```

4. Check: `https://<bot-url>/api`  
   - `"version": "3.28.1"`  
   - `"use_metaapi": false`  
   - `"trading_backend": "agent"`

## 2) Windows VPS supervisor ON
See `OWNER_GO_LIVE.md` / `vps_supervisor/README.md`  
`START_HERE.bat` window open rakho.

## 3) Test
1. Admin login → MT5 connect → **Start Bot** (VPS agent tabhi start)  
2. Badge: **MT5 Live** / **MT5 Connected (VPS)**  
3. Test follower same  
4. Master trade → follower copy  

## 4) Group
Website = `proactive-healing` public URL.  
Users: register → MT5 login → Start Bot. PC agent nahi.
