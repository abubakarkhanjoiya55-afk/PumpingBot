# Windows VPS Supervisor — mobile users, auto MT5 agents

**Owner quick guide:** [`../OWNER_GO_LIVE.md`](../OWNER_GO_LIVE.md)

Users **sirf mobile** se website pe MT5 login karte hain.  
Tumhara **1 Windows VPS** sabke agents khud start karta hai. MetaAPI nahi.

### Fastest start on a new VPS
1. `powershell -ExecutionPolicy Bypass -File setup_vps.ps1`
2. Edit `config.bat` (`SERVER_URL` + `VPS_SECRET`)
3. Put portable MT5 in `C:\PumpingBot\MT5_Template\`
4. Run `START_HERE.bat` (keep open)

```
Mobile user → website login/MT5 connect
        ↓
Railway API (roster)
        ↓
Windows VPS supervisor
        ↓
portable MT5 per account + local_agent
        ↓
WebSocket copy fan-out (fast)
```

## One-time VPS setup

### 1) Windows VPS
- Windows Server / Windows 10+ VPS (2–4 GB RAM start; ~150–300 MB per user terminal)
- Install Python 3.11+
- Install Git

### 2) Clone repo
```bat
mkdir C:\PumpingBot
cd C:\PumpingBot
git clone https://github.com/abubakarkhanjoiya55-afk/PumpingBot.git
cd PumpingBot
pip install -r vps_supervisor\requirements.txt
pip install -r local_agent\requirements.txt
```

### 3) Portable MT5 template
1. Install MetaTrader 5 once  
2. Copy whole MT5 folder to:
   ```
   C:\PumpingBot\MT5_Template\
   ```
   (andar `terminal64.exe` hona chahiye)
3. Us folder mein empty file banao: `portable` (extension nahi)

Supervisor har user ke liye clone karega:
```
C:\PumpingBot\MT5_Instances\{login}\
```

### 4) Railway env
```
TRADING_BACKEND=agent
USE_METAAPI=0
VPS_SECRET=pick-a-long-random-string
```

### 5) Start supervisor on VPS
```bat
set SERVER_URL=https://YOUR-APP.up.railway.app
set VPS_SECRET=same-as-railway
set MT5_TEMPLATE_DIR=C:\PumpingBot\MT5_Template
set MT5_INSTANCES_DIR=C:\PumpingBot\MT5_Instances
set REPO_DIR=C:\PumpingBot\PumpingBot
vps_supervisor\start_supervisor.bat
```

Rakhna chahiye **hamesha ON** (Task Scheduler / NSSM service recommended).

## User experience (group)
1. Mobile pe website open  
2. Register / login  
3. MT5 login + password + server dalo  
4. Bot Start  
5. Bas — VPS pe agent auto start, trades copy

User PC pe kuch install nahi.

## APIs (supervisor)
| Endpoint | Purpose |
|----------|---------|
| `GET /admin/vps/roster` | users to host (+ MT5 creds) |
| `POST /admin/vps/agent-token/{id}` | JWT for agent WS |
| `POST /admin/vps/report` | status heartbeat |
| `GET /me/vps-status` | mobile status |

All `/admin/vps/*` need header: `X-VPS-Secret: ...`

## Tips
- Pehle **apna master** account connect + Bot Start karo  
- Phir 1 test follower se verify  
- Logs: `C:\PumpingBot\logs\agent_*.log`  
- Broker ne jaldi disconnect kiya to supervisor 10s mein restart karega  
