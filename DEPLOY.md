# PumpingBot Deployment Guide

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
