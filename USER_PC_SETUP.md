# PumpingBot — User PC Setup (Follower)

Admin ka **ek master account** trades karta hai.  
Aapke **Windows PC** pe chhoti agent file chalti hai → aapke Exness account pe **same trades copy** hoti hain.

**VPS ki zaroorat nahi** (user ke liye).  
**PC din-raat ON** + internet zaroori.

---

## Join ke baad aapko kya karna hai (step by step)

### A) App pe (mobile ya browser)

1. PumpingBot app pe **Register / Login** karo.
2. **MT5** page kholo → apna Exness **Login, Password, Server** save karo.
3. **PC Setup** page pe jao → **Get Agent Token** dabao → token **copy** karo (30 din valid).
4. Baad mein Dashboard pe **Start Bot** tab dabana jab PC agent online ho.

### B) Windows PC pe (trades yahan lagenge)

5. PC pe **MetaTrader 5 (Exness)** install karo aur **usi account** se login karo jo app pe save kiya.
6. MT5 menu: **Tools → Options → Expert Advisors**
   - ✅ **Allow algorithmic trading**
   - ✅ DLL imports (agar option ho)
7. Windows **Sleep / Hibernate OFF** karo (Power Options).
8. Is repo ka folder PC pe rakho (zip ya `git clone`).
9. Command Prompt / PowerShell:

```bat
cd C:\path\to\PumpingBot
pip install -r local_agent\requirements.txt
```

10. `local_agent\START_FOLLOWER.bat` Notepad se kholo aur set karo:

| Variable | Example |
|----------|---------|
| `SERVER_URL` | `https://web-production-c78a0.up.railway.app` |
| `ACCESS_TOKEN` | (app se Get Agent Token) |
| `MT5_LOGIN` | aapka login number |
| `MT5_PASSWORD` | investor/trading password (jo MT5 API allow kare) |
| `MT5_SERVER` | e.g. `Exness-MT5Real…` |
| `MT5_PATH` | optional — agar ek hi MT5 hai to khali chhod sakte ho; warna `C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe` |

11. **START_FOLLOWER.bat** double-click karo.  
    Black window **band mat karo** — yahi agent hai.
12. App Dashboard pe badge **MT5 Live / Agent online** aaye.
13. **Start Bot** dabao.

Ab jab master trade karega, aapke PC ke MT5 pe copy trade lagegi.

---

## Rozana payment (25% profit → Admin)

1. Din ke **winning closed trades** ka **25%** admin ko bhejo (USDT BEP20 — app pe address dikhega).
2. App → **Payment / Subscription** page pe **screenshot upload**.
3. **Admin Approve** kare → **usi din / agla din** trades unlock.
4. **Bina admin approve** ke nayi trades **band** rehti hain.
5. Naya din (PKT midnight) pe unlock expire — dobara approve / daily unlock chahiye.

---

## Agar trades nahi lag rahi

| Check | |
|-------|--|
| PC on + agent window open? | Zaroori |
| MT5 logged in + Algo Trading ON? | Zaroori |
| App pe Start Bot ON? | Zaroori |
| Daily unlock / 25% paid + admin approve? | Zaroori |
| Internet / Railway app online? | Zaroori |

---

## Master (Admin) PC

Admin apne PC pe **master** agent chalata hai (`AGENT_ROLE=master`) — sirf **ek** strategy account.  
Followers alag-alag apne PC pe `AGENT_ROLE=follower` chalate hain.
