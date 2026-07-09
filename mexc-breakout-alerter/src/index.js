import { config } from "./config.js";
import { notifyStatus } from "./notify.js";
import { runScan } from "./scanner.js";
import { startWebServer } from "./server.js";

const once = process.argv.includes("--once");

console.log("╔══════════════════════════════════════════╗");
console.log("║   MEXC 4H Breakout Alerter (no trade)    ║");
console.log("╚══════════════════════════════════════════╝");
console.log(`Lookback: ${config.lookback} candles | Interval: 4h`);
console.log(`Phone alerts: ${notifyStatus()}`);
console.log(`Scan every: ${config.scanIntervalMs / 1000}s`);

if (config.webEnabled && !once) {
  startWebServer();
}

async function loop() {
  await runScan();
  if (once) {
    console.log("[EXIT] --once complete");
    process.exit(0);
  }
}

await loop();

if (!once) {
  setInterval(loop, config.scanIntervalMs);
}
