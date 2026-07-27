# Voltix (Voltix Exchange)

Branded URL: **https://voltix.exchange**

Live app (Railway): https://voltix-production-ecd8.up.railway.app

## Make voltix.exchange show Volt (pick ONE)

### A) Spaceship DNS → Railway (full stack, best)

1. [Spaceship](https://www.spaceship.com) → Domains → `voltix.exchange` → DNS
2. Delete Vercel A records (`76.76.21.21`)
3. Add:
   - `@` ALIAS/CNAME → `voltix-production-ecd8.up.railway.app`
   - `www` CNAME → `voltix-production-ecd8.up.railway.app`
4. Railway → service **voltix** → Networking → Custom Domain → add `voltix.exchange` + `www`

### B) Vercel (DNS already points here)

1. [Vercel](https://vercel.com) → project that owns `voltix.exchange`
2. Root Directory = `voltix` → Redeploy
3. Or add GitHub secrets `VERCEL_TOKEN` + `VERCEL_ORG_ID` + `VERCEL_PROJECT_ID` and push

Admin: `admin@voltix.exchange` / `VoltixAdmin@2026`
# Trigger Vercel deployment
