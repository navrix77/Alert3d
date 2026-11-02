// Кеш оболонки застосунку; дані про цілі завжди з мережі (застарілі цілі гірші за відсутні).
const C='tryvoga-v73';const SHELL=['/','/index.html','/style.css','/app.js','/perf.js','/sound.js','/arsenal.js','/cine.js','/fx.js','/holo.js','/icons.js','/models3d.js','/sprites/t-shahed.png','/sprites/t-jet.png','/sprites/t-cruise.png','/sprites/t-ballistic.png','/sprites/t-kab.png','/sprites/t-molniya.png','/manifest.webmanifest','/brand/emblem.png','/brand/icon-192.png','/brand/icon-192.png','/data/oblasts.geojson','/data/raions.geojson'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(C).then(c=>c.addAll(SHELL)));self.skipWaiting();});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==C).map(k=>caches.delete(k)))));self.clients.claim();});
self.addEventListener('fetch',e=>{const u=new URL(e.request.url);
  if(u.origin!==location.origin||u.pathname.startsWith('/api')||u.pathname==='/ws')return;
  e.respondWith(fetch(e.request).then(r=>{const cp=r.clone();caches.open(C).then(c=>c.put(e.request,cp));return r;}).catch(()=>caches.match(e.request)));});
