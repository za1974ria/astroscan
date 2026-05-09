const CACHE = 'astroscan-v158';

const PRECACHE = [];

// Phase O-E (2026-05-07) : pages qui ne doivent JAMAIS être servies depuis
// le cache — force le réseau pour éviter de servir du HTML obsolète qui aurait
// pu être mis en cache par une version antérieure du SW.
const NO_CACHE_PATHS = ['/portail', '/observatoire', '/landing', '/'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(PRECACHE)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  // APIs live → toujours réseau
  if (url.pathname.startsWith('/api/')) {
    e.respondWith(
      fetch(e.request).catch(() =>
        new Response(JSON.stringify({error:'offline'}),
          {headers:{'Content-Type':'application/json'}})
      )
    );
    return;
  }

  // Pages "shell" critiques → strict network-only, jamais de cache HTML.
  // Évite que du HTML obsolète (ex: sidebar dupliquée) soit servi.
  if (e.request.mode === 'navigate' && NO_CACHE_PATHS.includes(url.pathname)) {
    e.respondWith(fetch(e.request));
    return;
  }

  // Autres pages → Network First (cache fallback offline uniquement)
  if (e.request.mode === 'navigate') {
    e.respondWith(
      fetch(e.request)
        .then(res => {
          caches.open(CACHE).then(c => c.put(e.request, res.clone()));
          return res;
        })
        .catch(() => caches.match(e.request).then(r => r || caches.match('/')))
    );
    return;
  }

  // Assets → Cache First
  e.respondWith(
    caches.match(e.request).then(cached => {
      if (cached) return cached;
      return fetch(e.request).then(res => {
        if (res.status === 200)
          caches.open(CACHE).then(c => c.put(e.request, res.clone()));
        return res;
      });
    })
  );
});

self.addEventListener('push', e => {
  const data = e.data?.json() || {};
  self.registration.showNotification(data.title || 'AstroScan-Chohra', {
    body: data.body || 'Notification',
    icon: '/static/icons/icon-192.png',
    vibrate: [200,100,200],
    data: {url: data.url || '/'}
  });
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(clients.openWindow(e.notification.data.url || '/'));
});
