# PumpingBot Deployment Guide

Owner go-live (VPS): [`OWNER_GO_LIVE.md`](OWNER_GO_LIVE.md)  
Railway projects: [`RAILWAY_PROJECTS.md`](RAILWAY_PROJECTS.md)

---

## Layout

| Railway project | Role |
|-----------------|------|
| **`proactive-healing`** | MT5 PumpingBot |
| **`reasonable-essence`** | My Signals (+ Voltix) |

Merge first: https://github.com/abubakarkhanjoiya55-afk/PumpingBot/pull/47

---

## A) PumpingBot (`proactive-healing`)

1. Service `web` → branch **`main`** → root `Dockerfile`
2. Variables from `.env.bot.example`:
   ```
   TRADING_BACKEND=agent
   USE_METAAPI=0
   VPS_SECRET=long-random-secret
   EMBED_MY_SIGNALS=0
   MY_SIGNALS_URL=https://<my-signals-url>
   SECRET_KEY=...
   ```
3. Check `GET /api`:
   - `"version": "3.28.1"`
   - `"use_metaapi": false`
   - `"trading_backend": "agent"`

Windows VPS: `vps_supervisor/START_HERE.bat` (see `OWNER_GO_LIVE.md`).

---

## B) My Signals (`reasonable-essence`)

Full steps: [`my_signals_service/README.md`](my_signals_service/README.md)

1. Service **`web`** (rename optional → `my-signals`)
2. Dockerfile path: `my_signals_service/Dockerfile`
3. Variables:
   ```
   MY_SIGNALS_PREFIX=
   NTFY_TOPIC=pumpingbot-signals
   PORT=8000
   ```
4. Confirm `GET /api` → `"message": "My Signals API"`

**`voltix`** service mat chhero.

---

## C) Optional — Vercel frontend

Agar Railway same-origin UI use kar rahe ho → Vercel zaroori nahi.

Agar alag Vercel frontend:

1. Root Directory: `client`
2. Env: `VITE_API_URL` = **proactive-healing** bot URL  
   (example: `https://web-production-c78a0.up.railway.app`)  
   **My Signals URL (26ef9) mat dalo**

---

## Verify bot

1. Admin → MT5 connect → **Start Bot**
2. `GET /me/vps-status` → `vps_ready: true` (supervisor + agent up)
3. Follower same → master trade copies
