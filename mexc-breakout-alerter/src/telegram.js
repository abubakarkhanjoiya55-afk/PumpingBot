import { config, telegramConfigured } from "./config.js";

export async function sendTelegram(text) {
  if (!telegramConfigured()) return false;
  const url = `https://api.telegram.org/bot${config.telegram.token}/sendMessage`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chat_id: config.telegram.chatId,
      text,
      parse_mode: "HTML",
      disable_web_page_preview: true,
    }),
  });
  if (!res.ok) {
    const err = await res.text();
    console.error("[Telegram] fail:", err.slice(0, 300));
    return false;
  }
  return true;
}

export function formatAlertMessage(alert) {
  const emoji = alert.side === "BUY" ? "🟢" : "🔴";
  const time = new Date(alert.candleTime).toISOString().replace("T", " ").slice(0, 16);
  return (
    `${emoji} <b>MEXC 4H Breakout</b>\n` +
    `Coin: <b>${alert.symbol}</b>\n` +
    `Signal: ${alert.side} (${alert.direction})\n` +
    `Break level: ${alert.level}\n` +
    `Close: ${alert.close}\n` +
    `Range: ${alert.rangeLow} — ${alert.rangeHigh}\n` +
    `Strength: ${alert.strength}\n` +
    `Candle: ${time} UTC`
  );
}

export function formatConsoleLine(alert) {
  return `[BREAKOUT] ${alert.symbol} ${alert.side} @ ${alert.close} (level ${alert.level})`;
}
