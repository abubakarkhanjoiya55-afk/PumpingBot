# PumpingBot — User ke liye (bahut simple)

Aapko **Python / VPS / bat file** ki zaroorat **nahi**.

## Rozana sirf yeh 3 cheezein

1. PC pe **Exness MetaTrader 5** open  
2. Apna account **login**  
3. **Algo / AutoTrading ON**

Bas. Jab admin (master) trade karega, aapke MT5 pe copy trade EA khud laga degi — **agar aaj ka admin unlock + 25% clear ho**.

---

## Ek dafa setup (pehli baar)

### A) App (mobile/browser)

1. Register / Login  
2. **MT5** page pe apna Exness login / password / server **save**  
3. **PC Setup** pe jao → **EA Token** copy karo  
4. **Download EA** (`PumpingBotFollower.mq5`)

### B) Windows PC — Exness MT5

1. [Exness MT5](https://www.exness.com/apps/) download + install  
2. Apna account login  
3. **Tools → Options → Expert Advisors**
   - ✅ Allow algorithmic trading  
   - ✅ Allow WebRequest for listed URL → add:
     `https://web-production-c78a0.up.railway.app`  
     (ya jo bhi aapki app URL ho)
4. EA file copy karo:
   - MT5 → File → Open Data Folder → `MQL5\Experts\`
   - `PumpingBotFollower.mq5` yahan paste
5. Navigator (Ctrl+N) → Experts → refresh → **PumpingBotFollower** kisi chart pe drag  
6. Inputs:
   - `InpServerUrl` = app URL  
   - `InpToken` = app se copy kiya hua EA token  
7. OK → toolbar pe **AutoTrading** button green/ON  
8. Chart corner pe smiley / “PumpingBot EA: ONLINE”

PC **Sleep band** rakho jab trades chahiye.

---

## Rozana payment (25%)

- Din ke profit ka **25%** admin ko (USDT — app pe address)  
- Screenshot → **Payment** page  
- Admin **Approve** → agla / aaj unlock  
- Bina approve → EA trades **lock** (chart pe LOCKED dikhega)

---

## Trouble

| Problem | Fix |
|--------|-----|
| WebRequest failed | Options → EA → URL allow list |
| Token invalid | App → PC Setup → naya token EA mein |
| LOCKED | 25% pay + admin approve |
| No trades | Master trading? EA ONLINE? AutoTrading ON? |
