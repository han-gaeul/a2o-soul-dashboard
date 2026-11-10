// A2O SOUL Tracker 서비스 워커
// - 앱 화면(HTML·CSS·JS·아이콘): 네트워크 우선(배포 즉시 반영), 오프라인이면 캐시
// - 데이터(dashboard.json): 네트워크 우선, 오프라인이면 마지막 캐시
// - 썸네일·Chart.js·폰트: 캐시해두고 백그라운드 갱신
const VERSION = "v1";
const SHELL = `shell-${VERSION}`;
const RUNTIME = "runtime";
const SHELL_FILES = ["./", "index.html", "style.css", "app.js", "manifest.webmanifest",
  "icons/icon-192.png", "icons/icon-512.png", "icons/apple-touch-icon.png"];
const MAX_RUNTIME = 300;

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(SHELL_FILES)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    for (const key of await caches.keys()) if (key.startsWith("shell-") && key !== SHELL) await caches.delete(key);
    await self.clients.claim();
  })());
});

async function trim(cache) {
  const keys = await cache.keys();
  for (let i = 0; i < keys.length - MAX_RUNTIME; i++) await cache.delete(keys[i]);
}

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  // 데이터: 네트워크 우선
  if (url.pathname.endsWith("/data/dashboard.json")) {
    e.respondWith((async () => {
      const cache = await caches.open(RUNTIME);
      try {
        const res = await fetch(req, { cache: "no-store" });
        if (res.ok) cache.put(url.pathname, res.clone());
        return res;
      } catch (_) {
        return (await cache.match(url.pathname)) || Response.error();
      }
    })());
    return;
  }

  // 같은 출처의 앱 화면: 네트워크 우선(항상 최신), 오프라인이면 캐시
  if (url.origin === location.origin) {
    e.respondWith((async () => {
      const key = req.mode === "navigate" ? "index.html" : req;
      try {
        const res = await fetch(req, { cache: "no-cache" });
        if (res.ok) (await caches.open(SHELL)).put(key, res.clone());
        return res;
      } catch (_) {
        return (await caches.match(key)) || Response.error();
      }
    })());
    return;
  }

  // 썸네일·CDN·폰트: 캐시 즉시 응답 + 백그라운드 갱신
  if (/(^|\.)ytimg\.com$|cdnjs\.cloudflare\.com$|fonts\.(googleapis|gstatic)\.com$/.test(url.hostname)) {
    e.respondWith((async () => {
      const cache = await caches.open(RUNTIME);
      const hit = await cache.match(req);
      const net = fetch(req).then((res) => {
        if (res.ok || res.type === "opaque") cache.put(req, res.clone()).then(() => trim(cache));
        return res;
      }).catch(() => hit);
      return hit || net;
    })());
  }
});
