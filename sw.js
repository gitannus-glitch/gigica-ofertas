// Gigica Ofertas — service worker
// Guarda só a "casca" do site. Os arquivos de ofertas/histórico NUNCA ficam em cache
// (preço velho é proibido): sempre vão direto para a rede.
const VERSAO = "gigica-v1";
const CASCA = ["./", "index.html", "manifest.json", "icon-192.png", "icon-512.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSAO).then((c) => c.addAll(CASCA)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((ks) => Promise.all(ks.filter((k) => k !== VERSAO).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;

  // Dados de preço: sempre da rede, sem cache.
  if (/\/(ofertas|historico)\.json$/.test(url.pathname)) {
    e.respondWith(fetch(e.request, { cache: "no-store" }));
    return;
  }

  // Casca do site: rede primeiro (para pegar novas versões), cache se estiver offline.
  e.respondWith(
    fetch(e.request)
      .then((r) => {
        if (r.ok) { const cp = r.clone(); caches.open(VERSAO).then((c) => c.put(e.request, cp)); }
        return r;
      })
      .catch(() => caches.match(e.request).then((r) => r || caches.match("index.html")))
  );
});
