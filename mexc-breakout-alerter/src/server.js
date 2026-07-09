import http from "http";
import { readFileSync, existsSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import { config } from "./config.js";
import { getAlertHistory } from "./store.js";
import { onAlert } from "./scanner.js";

const publicDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "public");

const STATIC = {
  "/manifest.json": "application/manifest+json",
  "/sw.js": "application/javascript",
  "/icon-192.svg": "image/svg+xml",
  "/icon-512.svg": "image/svg+xml",
};

const sseClients = new Set();

function sendSse(client, data) {
  client.write(`data: ${JSON.stringify(data)}\n\n`);
}

function serveStatic(pathname, res) {
  const type = STATIC[pathname];
  if (!type) return false;
  const file = resolve(publicDir, pathname.slice(1));
  if (!existsSync(file)) return false;
  res.writeHead(200, { "Content-Type": type, "Cache-Control": "public, max-age=3600" });
  res.end(readFileSync(file));
  return true;
}

export function startWebServer() {
  const indexHtml = existsSync(resolve(publicDir, "index.html"))
    ? readFileSync(resolve(publicDir, "index.html"), "utf8")
    : "<h1>Device Care</h1>";

  onAlert((alert) => {
    const payload = { type: "breakout", alert };
    for (const client of sseClients) {
      sendSse(client, payload);
    }
  });

  const port = Number(process.env.PORT) || config.webPort;

  const server = http.createServer((req, res) => {
    const url = new URL(req.url, `http://localhost:${port}`);

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
          app: "Device Care",
          scanIntervalMs: config.scanIntervalMs,
          lookback: config.lookback,
        })
      );
      return;
    }

    if (serveStatic(url.pathname, res)) return;

    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    res.end(indexHtml);
  });

  server.on("error", (err) => {
    if (err.code === "EADDRINUSE") {
      console.error(`[WEB] Port ${port} already in use.`);
      process.exit(1);
    }
    throw err;
  });

  server.listen(port, "0.0.0.0", () => {
    console.log(`[APP] Device Care live on port ${port}`);
  });

  return server;
}
