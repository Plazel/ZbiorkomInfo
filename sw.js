// ZbiorkomInfo service worker: makes the site installable and keeps the last version of the page and the data used,
// so it opens without a connection too. Always the network first (fresh timetables), the stored copy when offline.
const C = 'zbiorkominfo-v4';
self.addEventListener('install', e => { e.waitUntil(caches.open(C).then(c => c.addAll(['./', 'index.html', 'manifest.webmanifest', 'icons/icon-192.png']).catch(() => {}))); self.skipWaiting(); });
self.addEventListener('activate', e => { e.waitUntil(caches.keys().then(k => Promise.all(k.filter(x => x !== C).map(x => caches.delete(x)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', e => {
  const r = e.request; if (r.method !== 'GET') return;
  const u = new URL(r.url); if (u.origin !== location.origin) return;   // map tiles and live data: straight from the network
  // (the page and its data asked of the server every time, not taken from the browser's cache for up to 10 minutes:
  // an unchanged file costs only a short "not modified" answer)
  const fresh = /\.(json|html)$|\/$/.test(u.pathname) ? new Request(r, { cache: 'no-cache' }) : r;
  const net = () => fetch(fresh).then(res => { if (res.ok) { const cp = res.clone(); caches.open(C).then(c => c.put(r, cp)); } return res; });
  // the timetables' data (the index, the lines, the maps, the duties): the stored copy at once, the server asked meanwhile for the
  // next time – the page opens without waiting for several MB; the notices, the live data, version.json and the page: the network first
  if (/\/data\//.test(u.pathname) && !/alerts_|_live|\/rt\/|version\.json|wymowa\.json/.test(u.pathname)) {
    // (a stored copy older than 6 hours – the data may have changed overnight, and files kept on different days need not
    // match one another –: the network first, the stored copy only if the network fails)
    e.respondWith(caches.open(C).then(c => c.match(r)).then(m => { const p = net().catch(() => m);
      const age = m ? Date.now() - (Date.parse(m.headers.get('date') || '') || 0) : Infinity;
      if (m && age < 6 * 3600e3) { e.waitUntil(p.catch(() => {})); return m; } return p.then(x => x || m); }));
    return;
  }
  e.respondWith(net().catch(() => caches.match(r).then(m => m || caches.match('index.html'))));
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
