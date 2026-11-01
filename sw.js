// ZbiorkomInfo service worker: makes the site installable and keeps the last version of the page and the data used,
// so it opens without a connection too. Always the network first (fresh timetables), the stored copy when offline.
const C = 'zbiorkominfo-v2';
self.addEventListener('install', e => { e.waitUntil(caches.open(C).then(c => c.addAll(['./', 'index.html', 'manifest.webmanifest', 'icons/icon-192.png']).catch(() => {}))); self.skipWaiting(); });
self.addEventListener('activate', e => { e.waitUntil(caches.keys().then(k => Promise.all(k.filter(x => x !== C).map(x => caches.delete(x)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', e => {
  const r = e.request; if (r.method !== 'GET') return;
  const u = new URL(r.url); if (u.origin !== location.origin) return;   // map tiles and live data: straight from the network
  e.respondWith(fetch(r).then(res => { if (res.ok) { const cp = res.clone(); caches.open(C).then(c => c.put(r, cp)); } return res; })
    .catch(() => caches.match(r).then(m => m || caches.match('index.html'))));
});
// the guide's notification (announcements on): its tap opens the app at the guide, its button mutes the announcements
self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(cs => {
    const c = cs[0];
    if (e.action === 'mute') { if (c) c.postMessage('gd-mute'); return; }
    if (c) { c.postMessage('gd-open'); return c.focus(); }
    return self.clients.openWindow((e.notification.data && e.notification.data.url) || './');
  }));
});
