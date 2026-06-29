/** Service worker: cache static game assets; network-first shell JS/CSS for fresh deploys. */
const CACHE_VERSION = "waifu-webapp-v43";
const SHELL_CACHE = `${CACHE_VERSION}-shell`;
const STATIC_CACHE = `${CACHE_VERSION}-static`;

/**
 * Precache offline fallback only; HTML is not precached (always network).
 * Pages request these with a ?v=waifu-webapp-vNN cache-busting query, so all
 * cache lookups below use { ignoreSearch: true } to match these query-less keys.
 */
const SHELL_URLS = [
  "/webapp/app.js",
  "/webapp/styles.css",
  "/webapp/bundle/app.min.js",
  "/webapp/bundle/styles.min.css",
  "/webapp/bundle/dungeons.min.js",
  "/webapp/bundle/tavern.min.js",
  "/webapp/bundle/combat-island.min.js",
  "/webapp/assets/tutorial.js",
  "/webapp/assets/tutorial.css",
  "/webapp/vendor/telegram-web-app.js",
  "/webapp/pages/tavern.js",
  "/webapp/pages/dungeons.js",
];

function isShellAsset(pathname) {
  if (!pathname.startsWith("/webapp/")) return false;
  return (
    pathname.endsWith(".js") ||
    pathname.endsWith(".css") ||
    pathname.endsWith(".webp") ||
    pathname.endsWith(".png") ||
    pathname.endsWith(".mp3")
  );
}

async function networkFirstShell(cache, req) {
  try {
    const res = await fetch(req);
    if (res.ok) await cache.put(req, res.clone());
    return res;
  } catch (err) {
    // Fall back to the precached version (stored without the ?v= query).
    const cached = await cache.match(req, { ignoreSearch: true });
    if (cached) return cached;
    throw err;
  }
}

async function cacheFirstStatic(cache, req) {
  const cached = await cache.match(req);
  if (cached) {
    fetch(req)
      .then((res) => {
        if (res.ok) cache.put(req, res.clone());
      })
      .catch(() => undefined);
    return cached;
  }
  try {
    const res = await fetch(req);
    if (res.ok) await cache.put(req, res.clone());
    return res;
  } catch (err) {
    throw err;
  }
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL_URLS).catch(() => undefined))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k.startsWith("waifu-webapp-") && k !== SHELL_CACHE && k !== STATIC_CACHE)
          .map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== "GET") return;
  if (url.pathname.startsWith("/api/")) return;

  if (url.pathname.startsWith("/static/game/")) {
    event.respondWith(
      caches.open(STATIC_CACHE).then((cache) => cacheFirstStatic(cache, req))
    );
    return;
  }

  if (
    url.pathname.startsWith("/static/guild_banners/") ||
    url.pathname.startsWith("/static/guild_icons/")
  ) {
    event.respondWith(
      caches.open(STATIC_CACHE).then((cache) => cacheFirstStatic(cache, req))
    );
    return;
  }

  if (isShellAsset(url.pathname)) {
    event.respondWith(caches.open(SHELL_CACHE).then((cache) => networkFirstShell(cache, req)));
  }
});
