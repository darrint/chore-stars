const CACHE = "chore-stars-v1";
const SHELL = ["/static/style.css", "/static/app.js", "/static/icon.svg", "/manifest.json"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)));
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.pathname.startsWith("/static/") || url.pathname === "/manifest.json") {
    event.respondWith(caches.match(event.request).then((hit) => hit || fetch(event.request)));
  }
});
