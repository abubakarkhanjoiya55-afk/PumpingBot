import { config } from "./config.js";

/**
 * 4H confirmed breakout — sirf band hui candle (-2 index).
 * Forming candle (-1) range mein shamil nahi.
 */
export function detect4hBreakout(ohlc) {
  const { opens, highs, lows, closes } = ohlc;
  const lb = config.lookback;
  if (closes.length < lb + 3) return null;

  const recentHigh = Math.max(...highs.slice(-lb - 1, -1));
  const recentLow = Math.min(...lows.slice(-lb - 1, -1));
  const rangeHeight = recentHigh - recentLow;
  if (rangeHeight <= 0) return null;

  const i = closes.length - 2;
  const open = opens[i];
  const close = closes[i];
  const high = highs[i];
  const low = lows[i];
  const prevClose = closes[i - 1];
  const body = Math.abs(close - open);
  const ranges = [];
  for (let j = Math.max(0, highs.length - 12); j < highs.length - 1; j++) {
    ranges.push(highs[j] - lows[j]);
  }
  const avgRange = ranges.reduce((a, b) => a + b, 0) / (ranges.length || 1) || 1;
  const strongMove = body >= avgRange * 0.35;

  if (close > recentHigh && prevClose <= recentHigh && strongMove) {
    return {
      direction: "BULLISH",
      side: "BUY",
      name: "4H Bullish Breakout",
      level: recentHigh,
      close,
      rangeHigh: recentHigh,
      rangeLow: recentLow,
      candleTime: ohlc.times[i],
      strength: Math.min(100, 40 + Math.round((body / avgRange) * 10)),
    };
  }

  if (close < recentLow && prevClose >= recentLow && strongMove) {
    return {
      direction: "BEARISH",
      side: "SELL",
      name: "4H Bearish Breakout",
      level: recentLow,
      close,
      rangeHigh: recentHigh,
      rangeLow: recentLow,
      candleTime: ohlc.times[i],
      strength: Math.min(100, 40 + Math.round((body / avgRange) * 10)),
    };
  }

  return null;
}
