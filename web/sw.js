// Кеш оболонки застосунку; дані про цілі завжди з мережі (застарілі цілі гірші за відсутні).
const C='tryvoga-v255';const SHELL=['/','/index.html','/style.css','/app.js','/perf.js','/sound.js','/arsenal.js','/live.js','/widget.js','/cine.js','/fx.js','/icons.js','/models3d.js','/sprites/t-shahed.png','/sprites/t-jet.png','/sprites/t-cruise.png','/sprites/t-ballistic.png','/sprites/t-kab.png','/sprites/t-molniya.png','/manifest.webmanifest','/brand/emblem.png','/brand/icon-192.png','/brand/badge-96.png','/data/oblasts.geojson','/data/raions.geojson'];
// Кешуємо кожен файл окремо й не валимо встановлення через один збій: addAll відхиляє ВСЕ при дублікаті чи 404,
// і тоді служба не стартує зовсім (03.11: дубль icon-192 у списку → push не працював, «служба сповіщень не запустилась»).
self.addEventListener('install',e=>{self.skipWaiting();e.waitUntil(caches.open(C).then(c=>Promise.all([...new Set(SHELL)].map(u=>c.add(u).catch(()=>{})))));});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==C).map(k=>caches.delete(k)))));self.clients.claim();});
self.addEventListener('fetch',e=>{const u=new URL(e.request.url);
  if(u.origin!==location.origin||u.pathname.startsWith('/api')||u.pathname==='/ws')return;
  e.respondWith(fetch(e.request,{cache:'no-cache'}).then(r=>{const cp=r.clone();caches.open(C).then(c=>c.put(e.request,cp));return r;}).catch(()=>caches.match(e.request)));});

// Web Push: сповіщення сервера навіть із закритим сайтом / заблокованим екраном
self.addEventListener('push',e=>{let d={};try{d=e.data?e.data.json():{};}catch(x){d={title:'NAVRYX SKY',body:e.data?e.data.text():''};}
  // рівень з першого символу заголовка: 🔴 — укриття (тримається на екрані, довга вібрація), 🟠 — курс на вас, 🟡 — можлива загроза, 🟢 — віддалились
  const t=d.title||'NAVRYX SKY',red=t.startsWith('🔴'),org=t.startsWith('🟠');
  e.waitUntil(self.registration.showNotification(t,{body:d.body||'',tag:d.tag||'navryx',renotify:red||org,icon:'/brand/icon-192.png',badge:'/brand/badge-96.png',
    timestamp:Date.now(),data:{url:d.url||'/'},...(d.image?{image:d.image}:{}),silent:false,requireInteraction:red||org,
    vibrate:red?[400,120,400,120,400,120,800]:org?[250,100,250,100,400]:[120,80,120],
    actions:[{action:'open',title:'Відкрити мапу'}]}));});
self.addEventListener('notificationclick',e=>{e.notification.close();const url=(e.notification.data&&e.notification.data.url)||'/';
  e.waitUntil(self.clients.matchAll({type:'window',includeUncontrolled:true}).then(cs=>{for(const c of cs){if('focus' in c)return c.focus();}return self.clients.openWindow(url);}));});
