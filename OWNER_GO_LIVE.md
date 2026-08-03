# Tumhara kaam — sirf itna (VPS buy ke baad)

Code ready hai. Users mobile se login karenge.  
**Sirf tum 1 Windows VPS chalaoge.**

Full Railway layout: [`RAILWAY_PROJECTS.md`](RAILWAY_PROJECTS.md) · short bot checklist: [`BOT_GO_LIVE.md`](BOT_GO_LIVE.md)

---

## A) Railway — pehle ye (`proactive-healing` = bot)

1. PR merge karo: https://github.com/abubakarkhanjoiya55-afk/PumpingBot/pull/47  
2. Railway project **`proactive-healing`** → service `web` → branch **`main`** → Redeploy  
3. Variables (`.env.bot.example` se):

```
TRADING_BACKEND=agent
USE_METAAPI=0
VPS_SECRET=apni-lambi-secret-yahan
EMBED_MY_SIGNALS=0
MY_SIGNALS_URL=https://<reasonable-essence-my-signals-url>
SECRET_KEY=...
```

4. Check: browser pe `https://YOUR-BOT.up.railway.app/api`  
   - `"version": "3.28.1"`  
   - `"use_metaapi": false`  
   - `"trading_backend": "agent"`

My Signals alag project: **`reasonable-essence`** → Dockerfile `my_signals_service/Dockerfile` (see `RAILWAY_PROJECTS.md`).

---

## B) Windows VPS buy (monthly, 1 saal mat lo)

- Type: **Windows** VPS (2–4 GB RAM start)
- Contabo / Hostinger jaisa provider
- RDP (Remote Desktop) access milna chahiye

---

## C) VPS pe 1-time setup (Remote Desktop se)

### 1) PowerShell Admin kholo, ye paste karo:

```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force
mkdir C:\PumpingBot -Force
cd C:\PumpingBot
# Agar git nahi: winget install Git.Git
git clone -b main --single-branch https://github.com/abubakarkhanjoiya55-afk/PumpingBot.git
# Agar main pe abhi merge nahi: -b cursor/my-signals-separate-service-ff4b
cd PumpingBot\vps_supervisor
powershell -ExecutionPolicy Bypass -File .\setup_vps.ps1
```

### 2) `config.bat` edit karo

File: `C:\PumpingBot\PumpingBot\vps_supervisor\config.bat`

```bat
set SERVER_URL=https://YOUR-BOT.up.railway.app
set VPS_SECRET=wahi-secret-jo-railway-pe-dalii
```

### 3) MetaTrader 5 template

1. VPS pe apne broker ka **MT5** install karo  
2. Poora install folder **copy** karke rakho:

```
C:\PumpingBot\MT5_Template\
```

Andar `terminal64.exe` dikhna chahiye.  
Us folder mein empty file banao: `portable` (extension nahi)

### 4) Supervisor start

Double-click:

```
C:\PumpingBot\PumpingBot\vps_supervisor\START_HERE.bat
```

**Ye window hamesha open / running rehni chahiye.**  
(PC restart pe phir se START_HERE.bat chalao, ya Task Scheduler laga dena)

---

## D) Test (group se pehle)

1. Mobile/PC pe **bot** website open (`proactive-healing` URL)  
2. Admin login → MT5 connect (master) → **Start Bot**  
3. Badge: **MT5 Live** / **MT5 Connected (VPS)**  
4. 1 test user se MT5 connect → **Start Bot**  
5. Master pe trade aaye → user pe copy dikhe  

Tab group ko website link bhejo.

---

## Group ko kya bolna hai

> App link pe aao → register → apna MT5 login/password/server dalo → Bot Start.  
> Phone se bas itna. PC pe kuch install nahi.

---

## Problem checklist

| Issue | Fix |
|--------|-----|
| Supervisor turant band | `config.bat` URL/secret check |
| MT5 template error | `C:\PumpingBot\MT5_Template\terminal64.exe` |
| User ready nahi | VPS window chal rahi hai? Railway `VPS_SECRET` same? Start Bot ON? |
| Purana API version | PR #47 merge + Railway redeploy → `3.28.1` |

Logs: `C:\PumpingBot\logs\`
