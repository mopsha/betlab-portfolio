// BetLab's service worker: pick alerts, and (Nov 4, idea #61) the last copy of each page for when there's no connection. The worker's
// `betlab alert` sends {title, body, url, tag}; tapping the notification opens (or focuses) BetLab at url.
const PAGES = "betlab-pages-1", STATIC = "betlab-static-1";
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil((async () => {
  for (const k of await caches.keys()) if (k !== PAGES && k !== STATIC) await caches.delete(k);
  await self.clients.claim();
})()));

/** What to do with a request: "static" (a build's file, its name never changes), "page" (try the network, keep the last copy), or
 *  null (leave it alone: live data, sign-in, anything that writes). */
function policy(url, method, mode, origin) {
  if (method !== "GET" || url.origin !== origin) return null;
  // a local preview: the dev server's file names aren't content-hashed, so a cached copy hid every style change (Nov 6)
  if (url.hostname === "localhost" || url.hostname === "127.0.0.1") return null;
  if (url.pathname.startsWith("/_next/static/")) return "static";
  if (mode !== "navigate" || url.pathname.startsWith("/api/") || url.pathname.startsWith("/auth") || url.pathname === "/login") return null;
  return "page";
}

const OFFLINE = `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BetLab</title>
<body style="font:16px system-ui;padding:32px;max-width:420px;margin:auto"><h1 style="font-size:22px">No connection</h1>
<p>This page hasn't been saved on this device yet. It will open once you're back online.</p></body>`;

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  const how = policy(url, event.request.method, event.request.mode, self.location.origin);
  if (how === "static") {
    event.respondWith((async () => {
      const cache = await caches.open(STATIC);
      const hit = await cache.match(event.request);
      if (hit) return hit;
      const res = await fetch(event.request);
      if (res.ok) await cache.put(event.request, res.clone());
      return res;
    })());
  } else if (how === "page") {
    event.respondWith((async () => {
      const cache = await caches.open(PAGES);
      try {
        const res = await fetch(event.request);
        // sent to sign-in: this device has no account now, so one account's pages must not open for the next
        if (res.redirected && new URL(res.url).pathname === "/login") await caches.delete(PAGES);
        else if (res.ok && !res.redirected) await cache.put(event.request, res.clone());
        // a server error (a database hiccup) is a resolved response, not a thrown one: the saved copy beats a blank page
        else if (res.status >= 500) return (await cache.match(event.request)) ?? res;
        return res;
      } catch {
        return (await cache.match(event.request)) ?? new Response(OFFLINE, { status: 503, headers: { "Content-Type": "text/html; charset=utf-8" } });
      }
    })());
  }
});

// Sign out (and the sign-in page) tell us to forget the saved pages: a server action's redirect isn't a navigation, so the
// "sent to sign-in" check above never sees it.
self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "signed-out") event.waitUntil(caches.delete(PAGES));
});

// Sign out and the sign-in page tell us to forget the saved pages (web/lib/offline.ts): a server action's redirect isn't
// a navigation, so the "sent to sign-in" check above never sees it.
self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "signed-out") event.waitUntil(caches.delete(PAGES));
});

self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch { data = { body: event.data && event.data.text() }; }
  event.waitUntil(self.registration.showNotification(data.title || "BetLab", {
    body: data.body || "", tag: data.tag, data: { url: data.url || "/" },
    icon: "/icons/icon-192.png", badge: "/icons/icon-192.png",
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL((event.notification.data && event.notification.data.url) || "/", self.location.origin).href;
  event.waitUntil((async () => {
    const open = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const c of open) {
      if (c.url.startsWith(self.location.origin)) {
        await c.focus();
        if ("navigate" in c) await c.navigate(url);
        return;
      }
    }
    await self.clients.openWindow(url);
  })());
});
