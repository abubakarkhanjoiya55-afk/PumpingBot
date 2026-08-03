# PumpingBot — tumhara kaam (VPS)

**Bot already live:** https://web-production-c78a0.up.railway.app  

Users mobile se login karenge. **Sirf tum 1 Windows VPS chalaoge.**

Short checklist: [`BOT_GO_LIVE.md`](BOT_GO_LIVE.md)

---

## A) Bot check (already done in code)

Browser: https://web-production-c78a0.up.railway.app/api  

```
"version": "3.28.3" (ya 3.28.x)
"use_metaapi": false
"trading_backend": "agent"
```

`VPS_SECRET` = `pumpingbot-vps-live-2026` (code + VPS `config.bat` — same)

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
cd PumpingBot\vps_supervisor
powershell -ExecutionPolicy Bypass -File .\setup_vps.ps1
```

### 2) `config.bat` edit karo

File: `C:\PumpingBot\PumpingBot\vps_supervisor\config.bat`

```bat
set SERVER_URL=https://web-production-c78a0.up.railway.app
set VPS_SECRET=pumpingbot-vps-live-2026
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

---

## D) Test (group se pehle)

1. Bot website: https://web-production-c78a0.up.railway.app  
2. Admin login → MT5 connect → **Start Bot**  
3. 1 test user → MT5 connect → **Start Bot**  
4. Master trade → user pe copy  

Tab group ko **bot** link bhejo.

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
| User ready nahi | VPS window chal rahi? Start Bot ON? |
| Purana API version | Railway redeploy / wait for GitHub deploy |

Logs: `C:\PumpingBot\logs\`
