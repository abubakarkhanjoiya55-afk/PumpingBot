# MEXC 4H Breakout Alerter

**Trade nahi** — sirf MEXC spot par 4H confirmed breakout dhundhta hai aur alert deta hai.

## Features

- MEXC public API (free, no API key for candles)
- 4H closed-candle breakout confirm
- WhatsApp notification (CallMeBot — free)
- Generic phone app alerts (NTFY — random app jaisa)
- Web dashboard + **alarm sound** (browser)
- Cooldown — same coin par dubara alert kam

---

## WSL Ubuntu — setup

### Option A — ek command (recommended)

WSL terminal mein **yeh poora block copy-paste** karo:

```bash
git clone https://github.com/abubakarkhanjoiya55-afk/PumpingBot.git ~/PumpingBot
cd ~/PumpingBot/mexc-breakout-alerter
bash setup-wsl.sh --run
```

Setup + server start ho jayega. Browser: **http://localhost:3847**

---

### Option B — manual

```bash
git clone https://github.com/abubakarkhanjoiya55-afk/PumpingBot.git ~/PumpingBot
cd ~/PumpingBot/mexc-breakout-alerter
cp .env.example .env
npm start
```

**Note:** Folder `~/mexc-breakout-alerter` nahi — path hai `~/PumpingBot/mexc-breakout-alerter`

### 3. Telegram (phone alerts)

1. Telegram → **@BotFather** → `/newbot` → token copy
2. Apne bot ko message bhejo
3. Browser: `https://api.telegram.org/bot<TOKEN>/getUpdates` → `chat.id` copy

`.env` mein:

```env
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=987654321
```

### 4. Chalao

```bash
npm start
```

**Terminal band mat karo** — server isi window mein chalta rehta hai.

Dashboard tab kholo jab yeh line aaye:

```
[WEB] Dashboard: http://localhost:3847
```

Windows browser (WSL se): `http://localhost:3847`

**Port already in use?**

```bash
pkill -f "node src/index.js"
npm start
```

Ya `.env` mein `WEB_PORT=3848` set karo.

Ek scan test:

```bash
npm run scan-once
```

---

## .env options

| Variable | Default | Meaning |
|----------|---------|---------|
| `SCAN_INTERVAL_MS` | 120000 | Har 2 min scan (4H candle slow hai) |
| `BREAKOUT_LOOKBACK` | 20 | Range ke liye 4H candles |
| `MIN_QUOTE_VOLUME_USDT` | 500000 | Kam volume coins skip |
| `MAX_SYMBOLS` | 0 | 0 = sab filtered coins |
| `ALERT_COOLDOWN_HOURS` | 8 | Dobara alert gap |
| `WEB_PORT` | 3847 | Dashboard port |
| `WEB_ENABLED` | true | Browser alarm |

---

## Breakout rule (4H)

1. Last **20** band hui 4H candles ka high/low = range
2. Latest **closed** 4H candle (forming nahi):
   - **Bullish:** close > range high + strong body
   - **Bearish:** close < range low + strong body
3. Alert: coin name + BUY/SELL + price

---

## WSL tip

Windows se browser:

```
http://localhost:3847
```

WSL2 usually port forward karta hai automatically.

Background mein chalana:

```bash
nohup npm start > scanner.log 2>&1 &
```

Band karna:

```bash
pkill -f "node src/index.js"
```

---

## PumpingBot se alag

Yeh project alag hai — MT5/MetaApi/trading se koi link nahi.
