const CACHE_NAME = "vocab-v1";
const API_CACHE_NAME = "vocab-api-v1";
const STATIC_ASSETS = ["/", "/index.html", "/app.js", "/style.css", "/manifest.json"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== CACHE_NAME && k !== API_CACHE_NAME)
          .map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;

  // Only handle GET requests
  if (request.method !== "GET") return;

  const url = new URL(request.url);

  // API requests (cross-origin backend): network-first, fall back to cache
  if (url.pathname.startsWith("/vocabulary") || url.pathname === "/health") {
    event.respondWith(networkFirst(request));
    return;
  }

  // Cross-origin requests to the backend host (when API_URL differs from PWA host)
  if (url.origin !== self.location.origin) {
    event.respondWith(networkFirst(request));
    return;
  }

  // Same-origin static assets: cache-first
  event.respondWith(cacheFirst(request));
});

async function networkFirst(request) {
  try {
    const response = await fetch(request); // GET-only path; no body to clone
    const cache = await caches.open(API_CACHE_NAME);
    cache.put(request, response.clone());
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;
    return new Response(
      JSON.stringify({ error: "Offline — no cached data available." }),
      { status: 503, headers: { "Content-Type": "application/json" } }
    );
  }
}

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    const cache = await caches.open(CACHE_NAME);
    cache.put(request, response.clone());
    return response;
  } catch {
    return new Response("Offline", { status: 503 });
  }
}
