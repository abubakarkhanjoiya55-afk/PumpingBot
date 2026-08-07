const BASE = self.registration.scope.replace(/\/$/, '').replace(self.location.origin, '') || "/my-signals";
const CACHE = "cps-v4.2.2";
const APP_VERSION = "4.2.2";
const PRECACHE = [
  `${BASE}/`,
  `${BASE}/manifest.json`,
  `${BASE}/icon-192.png`,
  `${BASE}/icon-512.png`,
];

self.addEventListener("install", (e) => {
  // Precache new assets but DO NOT activate immediately —
  // waiting SW lets the installed app keep running until user taps Update.
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(PRECACHE)));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys
          .filter((key) => (
            key !== CACHE && (
              key.startsWith("cps-") ||
              key.startsWith("my-signals-") ||
              key.startsWith("joy-signals-")
            )
          ))
          .map((key) => caches.delete(key))
      ))
      .then(() => self.clients.claim())
      .then(() => self.clients.matchAll({ type: "window" }))
      .then((clients) => {
        clients.forEach((c) => c.postMessage({ type: "SW_ACTIVATED", version: APP_VERSION }));
      })
  );
});

self.addEventListener("message", (e) => {
  const data = e.data || {};
  if (data.type === "SKIP_WAITING") {
    self.skipWaiting();
    return;
  }
  if (data.type === "GET_VERSION") {
    e.source && e.source.postMessage({ type: "SW_VERSION", version: APP_VERSION, cache: CACHE });
    return;
  }
  if (data.type !== "breakout") return;
  const a = data.alert;
  const title = "Crypto Pumping";
  const body = `${a.symbol} ${a.direction || ""} @ ${a.close}`;
  self.registration.showNotification(title, {
    body,
    icon: `${BASE}/icon-192.png`,
    badge: `${BASE}/icon-192.png`,
    vibrate: [300, 120, 300, 120, 300, 120, 500],
    tag: `bo-${a.symbol}`,
    renotify: true,
    requireInteraction: true,
    silent: false,
  });
});

self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET") return;
  if (e.request.url.includes("/events") || e.request.url.includes("/api/") || e.request.url.includes("/token") || e.request.url.includes("/me") || e.request.url.includes("/register")) {
    return;
  }
  // Network-first for HTML (so updates appear); cache fallback offline
  if (e.request.mode === "navigate" || e.request.headers.get("accept")?.includes("text/html")) {
    e.respondWith(
      fetch(e.request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(`${BASE}/`, copy));
          return response;
        })
        .catch(() => caches.match(`${BASE}/`))
    );
    return;
  }
  // Cache-first for static icons/manifest — refreshed on activate
  e.respondWith(
    caches.match(e.request).then((r) => r || fetch(e.request).then((res) => {
      const copy = res.clone();
      caches.open(CACHE).then((cache) => cache.put(e.request, copy));
      return res;
    }))
  );
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  e.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      if (list[0]) return list[0].focus();
      return self.clients.openWindow(`${BASE}/`);
    })
  );
});
