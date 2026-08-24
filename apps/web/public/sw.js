/* eslint-disable */
/**
 * キャッシュ戦略は docs/10-mobile-pwa.md §3.2。
 * キャッシュ表示時は必ず X-From-Cache と X-Fetched-At を付け、UI が取得時刻を出せるようにする。
 */
const VERSION = "v1";
const SHELL = "ai-stock-shell-" + VERSION;
const API = "ai-stock-api-" + VERSION;
const ASSETS = "ai-stock-assets-" + VERSION;
const PDF = "ai-stock-pdf-" + VERSION;

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL).then((cache) => cache.addAll(["/", "/manifest.webmanifest", "/icons/icon-192.svg"])),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => !k.endsWith(VERSION)).map((k) => caches.delete(k))),
    ),
  );
  self.clients.claim();
});

function withCacheHeaders(response, fetchedAt) {
  const headers = new Headers(response.headers);
  headers.set("X-From-Cache", "1");
  headers.set("X-Fetched-At", fetchedAt);
  return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
}

async function networkFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  try {
    const res = await fetch(request);
    if (res.ok) {
      const copy = res.clone();
      const headers = new Headers(copy.headers);
      headers.set("X-Fetched-At", new Date().toISOString());
      await cache.put(request, new Response(copy.body, { status: copy.status, headers }));
    }
    return res;
  } catch {
    const cached = await cache.match(request);
    if (cached) {
      const fetchedAt = cached.headers.get("X-Fetched-At") || cached.headers.get("date") || new Date(0).toISOString();
      return withCacheHeaders(cached, fetchedAt);
    }
    throw new Error("offline-uncached");
  }
}

async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  const network = fetch(request)
    .then((res) => {
      if (res.ok) void cache.put(request, res.clone());
      return res;
    })
    .catch(() => cached);
  if (cached) {
    void network;
    return cached;
  }
  return network;
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== "GET") return;
  if (url.pathname === "/api/v1/agent/events") return;
  if (url.pathname === "/api/v1/screener") return;

  if (url.pathname.startsWith("/api/v1/documents/") && url.pathname.endsWith("/file")) {
    event.respondWith(
      caches.open(PDF).then(async (cache) => {
        const hit = await cache.match(req);
        if (hit) return hit;
        const res = await fetch(req);
        if (res.ok) void cache.put(req, res.clone());
        return res;
      }),
    );
    return;
  }

  if (url.pathname.startsWith("/api/v1/")) {
    event.respondWith(networkFirst(req, API));
    return;
  }

  if (url.pathname.startsWith("/icons/") || url.pathname.endsWith(".woff2")) {
    event.respondWith(staleWhileRevalidate(req, ASSETS));
    return;
  }

  event.respondWith(staleWhileRevalidate(req, SHELL));
});

self.addEventListener("sync", (event) => {
  if (event.tag === "sync-trades") {
    event.waitUntil(
      self.clients.matchAll({ type: "window" }).then((clients) => {
        for (const client of clients) client.postMessage({ type: "flush-trades" });
      }),
    );
  }
});
