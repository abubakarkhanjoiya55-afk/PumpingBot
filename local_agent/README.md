# Local MT5 Agent

Yeh process **Windows VPS supervisor** khud chalata hai.  
Group users ko ye manually nahi chalana — woh sirf **mobile se MT5 login** karte hain.

Primary setup: **`../vps_supervisor/README.md`**

## Manual run (debug only)

```bat
set SERVER_URL=https://YOUR-APP.up.railway.app
set ACCESS_TOKEN=jwt-from-login
set MT5_LOGIN=12345678
set MT5_PASSWORD=...
set MT5_SERVER=Exness-MT5Trial15
set MT5_PATH=C:\PumpingBot\MT5_Instances\12345678\terminal64.exe
set AGENT_ROLE=follower
python local_agent\agent.py
```

Master ke liye `AGENT_ROLE=master`.

## Requirements
```bat
pip install -r local_agent\requirements.txt
```
