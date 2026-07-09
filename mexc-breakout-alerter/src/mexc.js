import { config } from "./config.js";

const INTERVAL = "4h";
const KLINE_LIMIT = 60;

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

/** USDT spot pairs — volume filter ke sath */
export async function getUsdtSymbols() {
  const tickers = await mexcGet("/api/v3/ticker/24hr");
  let list = tickers
    .filter((t) => {
      const sym = t.symbol || "";
      return sym.endsWith("USDT") && !sym.includes("_");
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
