const BASE = "/device-care";
const CACHE = "device-care-v3.17.0";
const PRECACHE = [
  `${BASE}/`,
  `${BASE}/manifest.json`,
  `${BASE}/icon-192.png`,
  `${BASE}/icon-512.png`,
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(PRECACHE)));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET") return;
  if (e.request.url.includes("/events") || e.request.url.includes("/api/")) {
    return;
  }
  if (e.request.mode === "navigate") {
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
  e.respondWith(
    caches.match(e.request).then((r) => r || fetch(e.request))
  );
});

self.addEventListener("message", (e) => {
  if (e.data?.type !== "breakout") return;
  const a = e.data.alert;
  const title = "Device Care";
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

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  e.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      if (list[0]) return list[0].focus();
      return self.clients.openWindow(`${BASE}/`);
    })
  );
});
