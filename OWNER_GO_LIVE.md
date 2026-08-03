# Tumhara kaam — sirf itna (VPS buy ke baad)

Code ready hai. Users mobile se login karenge.  
**Sirf tum 1 Windows VPS chalaoge.**

---

## A) Railway (website / API) — pehle ye

1. PR merge karo: https://github.com/abubakarkhanjoiya55-afk/PumpingBot/pull/45  
2. Railway pe deploy ho (GitHub `main` connect)  
3. Railway → Variables mein ye 3 daalo:

```
TRADING_BACKEND=agent
USE_METAAPI=0
VPS_SECRET=apni-lambi-secret-yahan
```

4. Check: browser pe `https://YOUR-APP.up.railway.app/api`  
   - `"version": "3.26.0"`  
   - `"use_metaapi": false`

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
git clone -b cursor/local-mt5-agent-hub-ff4b --single-branch https://github.com/abubakarkhanjoiya55-afk/PumpingBot.git
cd PumpingBot\vps_supervisor
powershell -ExecutionPolicy Bypass -File .\setup_vps.ps1
```

### 2) `config.bat` edit karo

File: `C:\PumpingBot\PumpingBot\vps_supervisor\config.bat`

```bat
set SERVER_URL=https://YOUR-APP.up.railway.app
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

1. Mobile/PC pe website open  
2. Admin login → MT5 connect (master) → Bot Start  
3. 1 test user se MT5 connect → Bot Start  
4. `GET /me/vps-status` ya dashboard pe ready dikhe  
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
| User ready nahi | VPS window chal rahi hai? Railway `VPS_SECRET` same? |
| Purana API version | PR merge + Railway redeploy |

Logs: `C:\PumpingBot\logs\`
