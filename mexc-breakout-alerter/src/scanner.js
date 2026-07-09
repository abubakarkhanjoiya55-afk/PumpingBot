import { getUsdtSymbols, getKlines4h } from "./mexc.js";
import { detect4hBreakout } from "./breakout.js";
import { isOnCooldown, setCooldown, saveAlert } from "./store.js";
import { sendAllAlerts, formatConsoleLine } from "./notify.js";

const listeners = new Set();

export function onAlert(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function broadcast(alert) {
  for (const fn of listeners) {
    try {
      fn(alert);
    } catch (e) {
      console.error("[broadcast]", e.message);
    }
  }
}

async function scanSymbol(symbol) {
  const ohlc = await getKlines4h(symbol);
  if (!ohlc) return null;

  const hit = detect4hBreakout(ohlc);
  if (!hit) return null;
  if (isOnCooldown(symbol, hit.direction)) return null;

  const alert = {
    id: `${symbol}-${hit.candleTime}-${hit.direction}`,
    symbol,
    ...hit,
    alertedAt: Date.now(),
  };

  setCooldown(symbol, hit.direction);
  saveAlert(alert);
  console.log("\n" + "═".repeat(50));
  console.log(formatConsoleLine(alert));
  console.log("═".repeat(50));

  await sendAllAlerts(alert);
  broadcast(alert);
  return alert;
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

/** Ek symbol ke baad chhota gap — rate limit */
const SYMBOL_DELAY_MS = 120;

export async function runScan() {
  const started = Date.now();
  console.log(`\n[SCAN] ${new Date().toLocaleString()} — MEXC 4H breakout scan...`);

  let symbols;
  try {
    symbols = await getUsdtSymbols();
  } catch (e) {
    console.error("[SCAN] symbols fetch failed:", e.message);
    return { alerts: [], error: e.message };
  }

  console.log(`[SCAN] ${symbols.length} USDT pairs (volume filter applied)`);

  const alerts = [];
  let errors = 0;

  for (let i = 0; i < symbols.length; i++) {
    const symbol = symbols[i];
    try {
      const a = await scanSymbol(symbol);
      if (a) alerts.push(a);
    } catch (e) {
      errors++;
      if (errors <= 3) console.warn(`[WARN] ${symbol}: ${e.message}`);
    }
    if (i < symbols.length - 1) await sleep(SYMBOL_DELAY_MS);
  }

  const sec = ((Date.now() - started) / 1000).toFixed(0);
  console.log(`[SCAN] Done in ${sec}s — ${alerts.length} new breakout(s), ${errors} errors`);
  return { alerts, symbols: symbols.length, errors };
}
