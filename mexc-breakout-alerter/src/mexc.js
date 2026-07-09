import { config } from "./config.js";

const INTERVAL = "4h";
const KLINE_LIMIT = 60;

const STABLE_FIAT_BASES = new Set([
  "USDC", "USDE", "USD1", "USDF", "DAI", "TUSD", "FDUSD", "BUSD",
  "EUR", "BRL", "EURI", "EURR", "GBP", "JPY", "AUD", "CAD", "CHF", "TRY",
  "XAUT", "PAXG",
]);

let apiSymbolsCache = null;
let symbolMetaCache = null;
let cacheAt = 0;
const CACHE_MS = 3600_000;

async function mexcGet(path) {
  const url = `${config.mexcBase}${path}`;
  const res = await fetch(url, {
    headers: { Accept: "application/json", "User-Agent": "MexcBreakoutAlerter/1.0" },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`MEXC ${res.status} ${path}: ${text.slice(0, 200)}`);
  }
  return res.json();
}

async function loadSymbolUniverse() {
  if (apiSymbolsCache && symbolMetaCache && Date.now() - cacheAt < CACHE_MS) {
    return { apiSymbols: apiSymbolsCache, meta: symbolMetaCache };
  }
  const [defaultRes, infoRes] = await Promise.all([
    mexcGet("/api/v3/defaultSymbols"),
    mexcGet("/api/v3/exchangeInfo"),
  ]);
  apiSymbolsCache = new Set(defaultRes.data || []);
  symbolMetaCache = Object.fromEntries(
    (infoRes.symbols || []).map((s) => [s.symbol, s])
  );
  cacheAt = Date.now();
  return { apiSymbols: apiSymbolsCache, meta: symbolMetaCache };
}

function isCryptoSpotUsdt(symbol, meta) {
  const s = meta[symbol];
  if (!s) return false;
  if (s.quoteAsset !== "USDT") return false;
  if (String(s.status) !== "1") return false;
  if (!s.isSpotTradingAllowed) return false;
  if (!s.permissions?.includes("SPOT")) return false;
  if (s.st) return false;
  if (/[()]/.test(symbol) || symbol.includes("_")) return false;
  const base = s.baseAsset || "";
  if (STABLE_FIAT_BASES.has(base)) return false;
  if (/^(GOLD|SILVER|OIL|GAS)/.test(base)) return false;
  return true;
}

/** MEXC API-tradable crypto/USDT spot pairs — volume filter ke sath */
export async function getUsdtSymbols() {
  const { apiSymbols, meta } = await loadSymbolUniverse();
  const tickers = await mexcGet("/api/v3/ticker/24hr");
  let list = tickers
    .filter((t) => {
      const sym = t.symbol || "";
      return apiSymbols.has(sym) && isCryptoSpotUsdt(sym, meta);
    })
    .map((t) => ({
      symbol: t.symbol,
      quoteVolume: Number(t.quoteVolume) || 0,
    }))
    .filter((t) => t.quoteVolume >= config.minQuoteVolume)
    .sort((a, b) => b.quoteVolume - a.quoteVolume);

  if (config.maxSymbols > 0) {
    list = list.slice(0, config.maxSymbols);
  }
  return list.map((t) => t.symbol);
}

/** 4H candles — Binance-style array */
export async function getKlines4h(symbol) {
  const data = await mexcGet(
    `/api/v3/klines?symbol=${symbol}&interval=${INTERVAL}&limit=${KLINE_LIMIT}`
  );
  if (!Array.isArray(data) || data.length < config.lookback + 3) {
    return null;
  }
  return {
    opens: data.map((c) => Number(c[1])),
    highs: data.map((c) => Number(c[2])),
    lows: data.map((c) => Number(c[3])),
    closes: data.map((c) => Number(c[4])),
    times: data.map((c) => Number(c[0])),
  };
}
