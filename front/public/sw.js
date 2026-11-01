// The offline shell: navigations go to the network, and the last app page it served is
// kept as '/' for when there is none. Every page of the SPA is the same index.html, so
// any successful navigation refreshes it (FP-07): the shell used to be cached once, at
// install, and an offline visit got the first build's index.html, whose hashed chunks
// later deploys had removed.
//
// Bump the version whenever this file's logic changes: the new name makes the browser
// install the new worker, and `activate` drops the older caches. nginx serves this file
// `no-cache`, so the change reaches every visitor on their next update check.
const CACHE_NAME = "majlisna-shell-v2";
const SHELL_URL = "/";
// Only the app's own index.html becomes the shell: the backend shares the origin and
// answers some navigations itself (/scalar, /openapi.json, /health).
const SHELL_MARKER = '<div id="root">';

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll([SHELL_URL])));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

function refreshShell(response) {
  // an opaque or redirect answer has status 0, so `ok` is false for it too
  if (!response.ok) return Promise.resolve();
  return response.text().then((html) => {
    if (!html.includes(SHELL_MARKER)) return undefined;
    return caches
      .open(CACHE_NAME)
      .then((cache) => cache.put(SHELL_URL, new Response(html, { status: 200, headers: response.headers })));
  });
}

function offlineShell() {
  return caches.match(SHELL_URL).then((cached) => cached || new Response("Offline", { status: 503 }));
}

self.addEventListener("fetch", (event) => {
  const { request } = event;

  // Only handle navigation requests (HTML pages)
  if (request.mode !== "navigate") return;

  event.respondWith(
    fetch(request).then(
      (response) => {
        // a copy for the cache; the page gets the original, unread
        event.waitUntil(refreshShell(response.clone()).catch(() => undefined));
        return response;
      },
      () => offlineShell()
    )
  );
});
