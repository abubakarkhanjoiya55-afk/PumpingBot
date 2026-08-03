# PumpingBot go-live (`proactive-healing`)

My Signals alag hai — is checklist mein **sirf bot**.

## Live check
Bot: https://web-production-c78a0.up.railway.app/api  

Chaahiye:
```json
{"message":"PumpingBot Smart API","version":"3.28.x","trading_backend":"agent","use_metaapi":false}
```

## Railway vars (optional — defaults already in code)
```
TRADING_BACKEND=agent
USE_METAAPI=0
VPS_SECRET=pumpingbot-vps-live-2026
```

## Windows VPS (owner — required for live copy)
1. Monthly Windows VPS + RDP  
2. Follow [`OWNER_GO_LIVE.md`](OWNER_GO_LIVE.md)  
3. `config.bat`:
   ```
   set SERVER_URL=https://web-production-c78a0.up.railway.app
   set VPS_SECRET=pumpingbot-vps-live-2026
   ```
4. MT5 template → `START_HERE.bat` hamesha chalata rakho  

## User test
1. Open bot URL → admin login → MT5 connect → **Start Bot**  
2. Test follower same  
3. Master trade → follower copy  
4. Group ko bot link do  
