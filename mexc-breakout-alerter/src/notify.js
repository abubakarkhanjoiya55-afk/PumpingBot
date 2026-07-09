import { config, whatsappConfigured, ntfyConfigured } from "./config.js";

export function formatAlertPlain(alert) {
  const emoji = alert.side === "BUY" ? "🟢" : "🔴";
  const time = new Date(alert.candleTime).toISOString().replace("T", " ").slice(0, 16);
  return (
    `${emoji} MEXC 4H Breakout\n` +
    `Coin: ${alert.symbol}\n` +
    `Signal: ${alert.side} (${alert.direction})\n` +
    `Break: ${alert.level} | Close: ${alert.close}\n` +
    `Range: ${alert.rangeLow} - ${alert.rangeHigh}\n` +
    `Strength: ${alert.strength}\n` +
    `Time: ${time} UTC`
  );
}

export function formatConsoleLine(alert) {
  return `[BREAKOUT] ${alert.symbol} ${alert.side} @ ${alert.close} (level ${alert.level})`;
}

/** WhatsApp — CallMeBot (free, personal alerts) */
export async function sendWhatsApp(text) {
  if (!whatsappConfigured()) return false;
  const phone = config.whatsapp.phone.replace(/\s/g, "");
  const params = new URLSearchParams({
    phone,
    text,
    apikey: config.whatsapp.apiKey,
  });
  const url = `https://api.callmebot.com/whatsapp.php?${params}`;
  try {
    const res = await fetch(url);
    const body = await res.text();
    if (!res.ok || body.toLowerCase().includes("error")) {
      console.error("[WhatsApp] fail:", body.slice(0, 200));
      return false;
    }
    return true;
  } catch (e) {
    console.error("[WhatsApp] fail:", e.message);
    return false;
  }
}

/**
 * NTFY — phone par generic app jaisa dikhta hai
 * Play Store: "ntfy" install → apne secret topic par subscribe
 */
export async function sendNtfy(alert) {
  if (!ntfyConfigured()) return false;
  const topic = config.ntfy.topic;
  const base = config.ntfy.server.replace(/\/$/, "");
  const title = config.ntfy.title;
  const body = `${alert.symbol} ${alert.side} @ ${alert.close}`;

  try {
    const res = await fetch(`${base}/${topic}`, {
      method: "POST",
      headers: {
        Title: title,
        Priority: "5",
        Tags: "alarm_clock,rotating_light",
      },
      body,
    });
    if (!res.ok) {
      console.error("[Alarm App] fail:", res.status);
      return false;
    }
    return true;
  } catch (e) {
    console.error("[Alarm App] fail:", e.message);
    return false;
  }
}

export async function sendAllAlerts(alert) {
  const text = formatAlertPlain(alert);
  const sentNtfy = await sendNtfy(alert);
  const sentWa = config.whatsapp.enabled ? await sendWhatsApp(text) : false;
  return sentNtfy || sentWa;
}

export function notifyStatus() {
  if (ntfyConfigured()) return `Alarm App (${config.ntfy.title})`;
  if (whatsappConfigured() && config.whatsapp.enabled) return "WhatsApp";
  return "OFF — .env mein NTFY_TOPIC set karo + phone par ntfy app";
}
