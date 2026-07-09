import { readFileSync, existsSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dir = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dir, "..");

function loadDotEnv() {
  const envPath = resolve(root, ".env");
  if (!existsSync(envPath)) return;
  for (const line of readFileSync(envPath, "utf8").split("\n")) {
    const t = line.trim();
    if (!t || t.startsWith("#")) continue;
    const i = t.indexOf("=");
    if (i < 1) continue;
    const key = t.slice(0, i).trim();
    const val = t.slice(i + 1).trim().replace(/^["']|["']$/g, "");
    if (!process.env[key]) process.env[key] = val;
  }
}

loadDotEnv();

export const config = {
  mexcBase: "https://api.mexc.com",
  scanIntervalMs: Number(process.env.SCAN_INTERVAL_MS) || 120_000,
  lookback: Number(process.env.BREAKOUT_LOOKBACK) || 20,
  minQuoteVolume: Number(process.env.MIN_QUOTE_VOLUME_USDT) || 500_000,
  maxSymbols: Number(process.env.MAX_SYMBOLS) || 0,
  cooldownHours: Number(process.env.ALERT_COOLDOWN_HOURS) || 8,
  webPort: Number(process.env.WEB_PORT) || 3847,
  webEnabled: process.env.WEB_ENABLED !== "false",
  whatsapp: {
    phone: process.env.WHATSAPP_PHONE || "",
    apiKey: process.env.WHATSAPP_API_KEY || "",
  },
  ntfy: {
    topic: process.env.NTFY_TOPIC || "",
    server: process.env.NTFY_SERVER || "https://ntfy.sh",
    title: process.env.NTFY_APP_TITLE || "System Service",
  },
};

export function whatsappConfigured() {
  return Boolean(config.whatsapp.phone && config.whatsapp.apiKey);
}

export function ntfyConfigured() {
  return Boolean(config.ntfy.topic);
}
