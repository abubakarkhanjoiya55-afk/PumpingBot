# Railway layout (tumhara plan)

| Railway project | Role | Service |
|-----------------|------|---------|
| **`proactive-healing`** | MT5 PumpingBot (trading / copy) | `web` |
| **`reasonable-essence`** | My Signals (+ Voltix) | `web` → rename/`my-signals`, `voltix` |

---

## A) `proactive-healing` = MT5 PumpingBot (rehne do)

Yeh naya project theek hai — **isi ko bot** rakho.

### Settings
- Repo: `PumpingBot`
- Dockerfile: root `Dockerfile` (default — mat badlo)
- Branch: `main` (PR merge ke baad) ya abhi feature branch

### Variables (bot)
```
TRADING_BACKEND=agent
USE_METAAPI=0
VPS_SECRET=apni-secret
EMBED_MY_SIGNALS=0
MY_SIGNALS_URL=https://<reasonable-essence-my-signals-url>
```

Bot URL example: `https://web-production-c78a0.up.railway.app`

---

## B) `reasonable-essence` → My Signals banao

Andar jo purana **`web`** hai (26ef9) — usko My Signals pe switch karo.  
**`voltix`** ko mat chhero.

### Steps (Railway UI)

1. Project **`reasonable-essence`** kholo  
2. Service **`web`** pe click  
3. **Settings**:
   - Service name → **`my-signals`** (optional lekin clear)
   - **Builder** → Dockerfile  
   - **Dockerfile path** → `my_signals_service/Dockerfile`  
   - Root Directory → blank / `/` (repo root)
4. **Variables** — PumpingBot wale hatao / ignore; ye rakho:
   ```
   MY_SIGNALS_PREFIX=
   MY_SIGNALS_VERSION=4.1.4
   NTFY_TOPIC=pumpingbot-signals
   PORT=8000
   SECRET_KEY=<long-random>
   ADMIN99_PASSWORD=Goku.k.g99
   ```
5. **Deploy** (Redeploy)

### Confirm
Browser:
`https://web-production-26ef9.up.railway.app/api`  
(ya naya domain jo Railway de)

Chaahiye:
```json
{ "message": "Crypto Pumping Signals API", "embedded_in_pumpingbot": false, "auth": true }
```

Agar ab bhi `"PumpingBot Smart API"` aaye → Dockerfile path abhi bhi root wala hai (galat).
Agar Railway `Application not found` (404) → project/service crash / credits / deleted — dashboard se Redeploy + domain check.
---

## C) Zaroori: code pehle merge

`my_signals_service/` abhi PR mein hai:
https://github.com/abubakarkhanjoiya55-afk/PumpingBot/pull/47

1. PR **merge** karo `main` pe  
2. Dono Railway projects ko branch **`main`** pe lagao  
3. Phir `reasonable-essence` pe Dockerfile path set karke redeploy

---

## Final picture

```
proactive-healing
  └── web          → PumpingBot MT5 bot

reasonable-essence
  ├── my-signals   → My Signals alerts PWA
  └── voltix       → Voltix (jaise pehle)
```

Users:
- Bot / trading → `proactive-healing` URL  
- Signals app → `reasonable-essence` My Signals URL  
