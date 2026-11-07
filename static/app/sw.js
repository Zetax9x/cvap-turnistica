// Service worker dell'app: tiene in cache solo i file dell'interfaccia. Le API vanno sempre in rete,
// così non si vedono mai turni vecchi. Strategia: rete prima, cache se il telefono è offline.
const CACHE = "cvap-app-v2";
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

// ---- notifiche push (il server manda {titolo, testo, url}; iOS pretende che ogni push mostri una notifica) ----
self.addEventListener("push", (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch { /* messaggio non leggibile: si mostra comunque l'avviso */ }
  e.waitUntil(self.registration.showNotification(d.titolo || "Turni CVAP", {
    body: d.testo || "", icon: "/app/img/icona-192.png", data: { url: d.url || "/app/" },
  }));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = new URL((e.notification.data && e.notification.data.url) || "/app/", self.location.origin).href;
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((finestre) => {
    const aperta = finestre.find((c) => new URL(c.url).pathname.startsWith("/app/"));
    if (aperta) return aperta.focus().then(() => aperta.navigate(url));
    return self.clients.openWindow(url);
  }));
});
