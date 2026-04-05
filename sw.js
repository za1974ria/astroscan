const CACHE = 'orbital-v3';
const STATIC = ['/', '/portail', '/dashboard'];
self.addEventListener('install', function(e) {
  e.waitUntil(caches.open(CACHE).then(function(c) { return c.addAll(STATIC).catch(function(){}); }));
  self.skipWaiting();
});
self.addEventListener('activate', function(e) {
  e.waitUntil(caches.keys().then(function(keys) {
    return Promise.all(keys.filter(function(k) { return k !== CACHE; }).map(function(k) { return caches.delete(k); }));
  }));
  self.clients.claim();
});
self.addEventListener('fetch', function(e) {
  var url = new URL(e.request.url);
  if (url.pathname.indexOf('/api/') === 0) {
    e.respondWith(fetch(e.request, { cache: 'no-store' }).catch(function() {
      return new Response(JSON.stringify({ ok: false, error: 'offline' }), { headers: { 'Content-Type': 'application/json' } });
    }));
    return;
  }
  e.respondWith(caches.match(e.request).then(function(cached) {
    var net = fetch(e.request).then(function(res) {
      if (res.ok) caches.open(CACHE).then(function(c) { c.put(e.request, res.clone()); });
      return res;
    });
    return cached || net;
  }));
});
