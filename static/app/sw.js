// Service worker dell'app: tiene in cache solo i file dell'interfaccia. Le API vanno sempre in rete,
// così non si vedono mai turni vecchi. Strategia: rete prima, cache se il telefono è offline.
const CACHE = "cvap-app-v1";
const BASE = ["/app/", "/app/app.css", "/app/js/main.js", "/app/manifest.webmanifest"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(BASE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((nomi) => Promise.all(nomi.filter((n) => n !== CACHE).map((n) => caches.delete(n))))
      .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const r = e.request;
  const url = new URL(r.url);
  if (r.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api/")) return;
  if (!url.pathname.startsWith("/app/") && !url.pathname.startsWith("/static/")) return;
  e.respondWith(
    fetch(r).then((risposta) => {
      if (risposta.ok) {
        const copia = risposta.clone();
        caches.open(CACHE).then((c) => c.put(r, copia));
      }
      return risposta;
    }).catch(() => caches.match(r, { ignoreSearch: true })));
});
