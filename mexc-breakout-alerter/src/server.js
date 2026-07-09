import http from "http";
import { readFileSync, existsSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import { config } from "./config.js";
import { getAlertHistory } from "./store.js";
import { onAlert } from "./scanner.js";
import { whatsappConfigured, ntfyConfigured } from "./config.js";

const publicDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "public");

const sseClients = new Set();

function sendSse(client, data) {
  client.write(`data: ${JSON.stringify(data)}\n\n`);
}

export function startWebServer() {
  const indexHtml = existsSync(resolve(publicDir, "index.html"))
    ? readFileSync(resolve(publicDir, "index.html"), "utf8")
    : "<h1>MEXC Alerter</h1>";

  onAlert((alert) => {
    const payload = { type: "breakout", alert };
    for (const client of sseClients) {
      sendSse(client, payload);
    }
  });

  const server = http.createServer((req, res) => {
    const url = new URL(req.url, `http://localhost:${config.webPort}`);

    if (url.pathname === "/events") {
      res.writeHead(200, {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
        "Access-Control-Allow-Origin": "*",
      });
      res.write(": connected\n\n");
      sseClients.add(res);
      req.on("close", () => sseClients.delete(res));
      return;
    }

    if (url.pathname === "/api/alerts") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify(getAlertHistory(80)));
      return;
    }

    if (url.pathname === "/api/status") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(
        JSON.stringify({
          ok: true,
          whatsapp: whatsappConfigured(),
          ntfy: ntfyConfigured(),
          scanIntervalMs: config.scanIntervalMs,
          lookback: config.lookback,
        })
      );
      return;
    }

    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    res.end(indexHtml);
  });

  server.on("error", (err) => {
    if (err.code === "EADDRINUSE") {
      console.error(`[WEB] Port ${config.webPort} already in use.`);
      console.error("[WEB] Fix: pkill -f 'node src/index.js'  OR  change WEB_PORT in .env");
      process.exit(1);
    }
    throw err;
  });

  server.listen(config.webPort, () => {
    console.log(`[WEB] Dashboard: http://localhost:${config.webPort}`);
    console.log("[WEB] Browser kholo — breakout par alarm bajega");
  });

  return server;
}
