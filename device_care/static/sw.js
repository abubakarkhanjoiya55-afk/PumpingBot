const CACHE = "device-care-v1";

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) =>
      c.addAll(["/", "/manifest.json", "/icon-192.svg", "/icon-512.svg"])
    )
  );
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (e) => {
  if (e.request.url.includes("/events") || e.request.url.includes("/api/")) {
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
  const body = `${a.symbol} ${a.side} @ ${a.close}`;
  self.registration.showNotification(title, {
    body,
    icon: "/icon-192.svg",
    badge: "/icon-192.svg",
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
    self.clients.matchAll({ type: "window" }).then((list) => {
      if (list[0]) return list[0].focus();
      return self.clients.openWindow("/");
    })
  );
});
