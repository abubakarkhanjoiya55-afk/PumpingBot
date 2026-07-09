import { readFileSync, writeFileSync, mkdirSync, existsSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import { config } from "./config.js";

const dataDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "data");
const cooldownPath = resolve(dataDir, "cooldown.json");
const historyPath = resolve(dataDir, "alerts.json");

function ensureDataDir() {
  if (!existsSync(dataDir)) mkdirSync(dataDir, { recursive: true });
}

function readJson(path, fallback) {
  ensureDataDir();
  if (!existsSync(path)) return fallback;
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch {
    return fallback;
  }
}

function writeJson(path, data) {
  ensureDataDir();
  writeFileSync(path, JSON.stringify(data, null, 2), "utf8");
}

export function isOnCooldown(symbol, direction) {
  const key = `${symbol}:${direction}`;
  const map = readJson(cooldownPath, {});
  const until = map[key];
  if (!until) return false;
  return Date.now() < until;
}

export function setCooldown(symbol, direction) {
  const key = `${symbol}:${direction}`;
  const map = readJson(cooldownPath, {});
  map[key] = Date.now() + config.cooldownHours * 3600 * 1000;
  writeJson(cooldownPath, map);
}

export function saveAlert(alert) {
  const list = readJson(historyPath, []);
  list.unshift(alert);
  writeJson(historyPath, list.slice(0, 200));
}

export function getAlertHistory(limit = 50) {
  return readJson(historyPath, []).slice(0, limit);
}
