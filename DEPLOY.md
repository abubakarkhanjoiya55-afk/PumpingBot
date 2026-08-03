# PumpingBot Deployment Guide

## My Signals — alag Railway service

Full steps: [`my_signals_service/README.md`](my_signals_service/README.md)

1. Railway pe naya service banao: **`my-signals`**
2. Dockerfile: `my_signals_service/Dockerfile` (repo root context)
3. PumpingBot `web` variables:
   ```
   MY_SIGNALS_URL=https://my-signals-....up.railway.app
   EMBED_MY_SIGNALS=0
   ```
4. Jab tak `MY_SIGNALS_URL` set nahi → My Signals purane `/my-signals` pe hi chalta rahega

---

## Trading backend (recommended): Windows VPS hosted agents — NO MetaAPI

**Owner checklist (VPS buy → go live):** [`OWNER_GO_LIVE.md`](OWNER_GO_LIVE.md)

**Users sirf mobile se MT5 login karte hain.**  
Tumhara 1 Windows VPS sabke agents auto chalata hai.

1. Railway env:
   ```
   TRADING_BACKEND=agent
   USE_METAAPI=0
   VPS_SECRET=long-random-secret
   ```
2. Windows VPS: `vps_supervisor/setup_vps.ps1` → `config.bat` → `START_HERE.bat`
3. Check:
   - `GET /api` → version `3.26.0`, `use_metaapi: false`
   - `GET /me/vps-status` (user token) → `vps_ready: true`
   - `GET /agents` → online agents

MetaAPI optional legacy (`USE_METAAPI=1`) — default off.

---

## ⚠️ IMPORTANT: Railway abhi GitHub se connected NAHI hai

Production abhi bhi purana code chala raha hai:
```
https://web-production-6a35f.up.railway.app/  →  "PumpingBot Smart API v2"
```

Naya code deploy hone ke baad yeh dikhega:
```json
{"message":"PumpingBot Smart API","version":"3.3.0",...}
```

Build ab **Dockerfile** se hota hai (nixpacks `pip: not found` fix).

GitHub pe sab push ho chuka hai — ab Railway + Vercel connect karna hai.

---

## Step 1 — Railway Backend (5 min)

1. [railway.app](https://railway.app) → Login
2. Apna **PumpingBot** project kholo
3. **Settings** → **Source** → **Connect GitHub**
4. Repo select karo: `abubakarkhanjoiya55-afk/PumpingBot`
5. Branch: **`main`**
6. **Deploy** / **Redeploy** dabao
7. Verify: `https://web-production-6a35f.up.railway.app/` → `"version":"3.3.0"`

Railway ab automatically:
- Python backend install karega
- React frontend build karega (`client/`)
- Dono ek saath serve karega

---

## Step 2 — Vercel Frontend (5 min)

### Option A — Existing project update (recommended)

1. [vercel.com](https://vercel.com) → `pumping-bot-frontend-two` project
2. **Settings** → **General** → **Root Directory** → set to: `client`
3. **Settings** → **Environment Variables**:
   - `VITE_API_URL` = `https://web-production-6a35f.up.railway.app`
4. **Deployments** → **Redeploy**

### Option B — GitHub auto-deploy (new push se automatic)

1. Vercel → **Add New Project** → Import `PumpingBot` from GitHub
2. Root Directory: `client`
3. Env: `VITE_API_URL` = `https://web-production-6a35f.up.railway.app`
4. Deploy

Root `vercel.json` already configured hai repo mein.

---

## Step 3 — Verify frontend fix

Dashboard pe yeh dikhna chahiye:
- **OPEN TRADES:** 6 (ya jitni chal rahi hon)
- **FLOATING P/L:** ~-$4.93 (red) — equity minus balance
- **Open Trades** page pe har trade ka P&L

---

## Optional — GitHub Actions auto-deploy

Repo secrets add karo (GitHub → Settings → Secrets):

| Secret | Kahan se milega |
|--------|----------------|
| `VERCEL_TOKEN` | vercel.com → Account → Tokens |
| `VERCEL_ORG_ID` | Vercel project settings |
| `VERCEL_PROJECT_ID` | Vercel project settings |
| `RAILWAY_TOKEN` | railway.app → Account → Tokens |

Phir har `main` push pe automatic deploy hoga.

---

## Kya fix hua (v3.2.0)

| Fix | Detail |
|-----|--------|
| DB sync | Live MT5 positions → DB `open` trades sync |
| Floating P/L | `equity - balance` calculate hota hai |
| Open positions | Saari live MT5 positions return hoti hain |
| New React UI | `client/` — Vercel ke liye fixed frontend |
