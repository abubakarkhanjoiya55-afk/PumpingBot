# PumpingBot Deployment Guide

## Problem: Frontend shows 0 open trades

The Vercel frontend counts **OPEN TRADES** from `/trades` where `status === "open"`.
If DB is out of sync with MT5, it shows 0 even when trades are running.

**Fix in v3.1.0:** Backend now auto-syncs DB with live MT5 on every `/me`, `/trades`, `/open_positions` call.

---

## Step 1 — Railway (Backend)

1. Railway Dashboard → your service → **Settings** → **Source**
2. Connect to GitHub repo: `abubakarkhanjoiya55-afk/PumpingBot`
3. Branch: **`main`**
4. Click **Redeploy**

**Verify deploy worked:**
```
https://web-production-6a35f.up.railway.app/
```
Should show: `"version": "3.1.0"` (NOT "v2")

---

## Step 2 — Vercel (Frontend) — NEW fixed frontend

The old Vercel frontend has bugs. Deploy the new one from this repo:

1. Vercel Dashboard → **Add New Project**
2. Import GitHub repo: `PumpingBot`
3. **Root Directory:** `client`
4. Environment Variable:
   - `VITE_API_URL` = `https://web-production-6a35f.up.railway.app`
5. Deploy

Or update existing Vercel project:
- Settings → Root Directory → `client`
- Redeploy

---

## What the new frontend fixes

| Issue | Old Vercel | New client/ |
|-------|-----------|-------------|
| Floating P/L shows $0 | Only uses `me.profit` | Falls back to `equity - balance` |
| Open Trades shows 0 | DB out of sync | Uses `max(trades.open, positions.length)` |
| Backend sync | None | `reconcile_trades_with_mt5()` on every API call |
