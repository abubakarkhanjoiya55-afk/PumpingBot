# SceneCut Pro — Permanent Live (Railway)

## LIVE NOW
- Editor: https://scenecut-production.up.railway.app/
- Download: https://scenecut-production.up.railway.app/download
- Health: https://scenecut-production.up.railway.app/health

Service: `scenecut` (Railway project)

---

Redeploy / repair ke liye **ek dafa** yeh setup helpful hai:

## Aapke sath 2-minute setup

### 1) Naya Account Token
1. Open: https://railway.app/account/tokens
2. **Create Token**
3. Team: **No Team** (Project token nahi — Account token)
4. GitHub repo → **Settings → Secrets and variables → Actions**
5. Secret update/create:
   - Name: `RAILWAY_TOKEN`
   - Value: naya token

### 2) Empty service banao (sirf ek dafa)
1. https://railway.app → apna PumpingBot project
2. **New → Empty Service**
3. Name: `scenecut`
4. Service Settings:
   - **Root Directory:** `auto_scene_cutter`
   - **Builder:** Dockerfile
5. **Networking → Generate Domain**
   - Example: `https://scenecut-production-xxxx.up.railway.app`

### 3) Deploy trigger
- PR merge to `main`, **ya**
- GitHub Actions → **Deploy SceneCut Pro** → Run workflow

Phir permanent links:
- Editor: `https://YOUR-DOMAIN.up.railway.app/`
- Download: `https://YOUR-DOMAIN.up.railway.app/download`
- Health: `https://YOUR-DOMAIN.up.railway.app/health`

## Local / temporary (already running)
Cloudflare quick tunnel (session-based):
`https://settings-vsnet-cheers-claims.trycloudflare.com`

## Files used for deploy
- `auto_scene_cutter/Dockerfile`
- `auto_scene_cutter/railway.toml`
- `auto_scene_cutter/start_web.sh`
- `scripts/railway-deploy-scenecut.sh`
- `.github/workflows/deploy-scenecut.yml`
