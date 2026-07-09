import http from "http";
import { readFileSync, existsSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import { config } from "./config.js";
import { getAlertHistory } from "./store.js";
import { onAlert } from "./scanner.js";
import { telegramConfigured } from "./config.js";

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
          telegram: telegramConfigured(),
          scanIntervalMs: config.scanIntervalMs,
          lookback: config.lookback,
        })
      );
      return;
    }

    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    res.end(indexHtml);
  });

  server.listen(config.webPort, () => {
    console.log(`[WEB] Dashboard: http://localhost:${config.webPort}`);
    console.log("[WEB] Browser kholo — breakout par alarm bajega");
  });

  return server;
}
