const CACHE = "shanklife-shell-1.9.58";
const PUBLIC_ASSETS = [
  "/static/style.css?v=1.9.58",
  "/static/shanklife-favicon.png",
  "/static/shanklife-icon-192.png",
  "/static/shanklife-icon-512.png",
  "/static/balletour-icon-192.png",
  "/static/balletour-icon-512.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(PUBLIC_ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)))).then(() => self.clients.claim()));
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin || !url.pathname.startsWith("/static/")) return;
  event.respondWith(caches.match(event.request).then((cached) => cached || fetch(event.request)));
});
