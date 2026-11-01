// «Небо в камері»: де відносно вас зараз цілі (азимут + приблизна висота кута), з курсом і часом до дому.
(() => {
  'use strict';
  const $ = s => document.querySelector(s);
  const D2R = Math.PI / 180, KX = 111.32 * Math.cos(49 * D2R), KY = 110.57;
  const xy = ([lon, lat]) => [(lon - 31.5) * KX, (lat - 49) * KY];
  const ll = ([x, y]) => [x / KX + 31.5, 49 + y / KY];
  const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
  const brg = (a, b) => (Math.atan2(b[0] - a[0], b[1] - a[1]) / D2R + 360) % 360;
  const angd = (a, b) => { let d = Math.abs(a - b) % 360; return d > 180 ? 360 - d : d; };
  const NAME = { shahed: 'Шахед', jet: 'Реактивний БпЛА', molniya: '«Молнія»', cruise: 'Крилата ракета', ballistic: 'Балістика' };
  const ALT = { shahed: 1.5, molniya: 0.8, jet: 3, cruise: 0.15, ballistic: 20 };
  const COL = { shahed: '#FF9F2E', jet: '#FF5FA2', molniya: '#FFD84A', cruise: '#FF4B3E', ballistic: '#C77DFF' };
  const HFOV = 62;
  const cv = $('#ov'), cx = cv.getContext('2d');
  let SNAP = null, offset = 0, home = null, az = 0, el = 20, hasOri = false, drag = null;
  const IMG = {};
  for (const t of Object.keys(NAME)) { const i = new Image(); i.src = 'sprites/t-' + t + '.png'; IMG[t] = i; }
  try { home = JSON.parse(localStorage.getItem('home') || 'null'); } catch (e) {}

  function posAt(tr, serverT) { // як у головному застосунку
    if (tr.status !== 'active') return [tr.lon, tr.lat];
    let km = tr.speed * Math.max(0, serverT - tr.ts) / 3600;
    const pts = [xy([tr.lon, tr.lat]), ...(tr.route || []).map(xy)];
    if (pts.length === 1) { if (tr.hd == null) return [tr.lon, tr.lat]; km = Math.min(km, tr.speed * 4 / 60); const r = tr.hd * D2R; return ll([pts[0][0] + Math.sin(r) * km, pts[0][1] + Math.cos(r) * km]); }
    let acc = 0; for (let i = 1; i < pts.length; i++) { const d = dist(pts[i - 1], pts[i]); if (acc + d >= km) { const f = (km - acc) / (d || 1); return ll([pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * f, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * f]); } acc += d; }
    return ll(pts[pts.length - 1]);
  }
  function load() { fetch('/api/state').then(r => r.json()).then(s => { SNAP = s; offset = s.now - Date.now() / 1000; }).catch(() => {}); }
  load(); setInterval(load, 3000);
  if (!home && navigator.geolocation) navigator.geolocation.getCurrentPosition(p => { home = [p.coords.longitude, p.coords.latitude]; }, () => {});

  function onOri(e) {
    let h = null;
    if (typeof e.webkitCompassHeading === 'number') h = e.webkitCompassHeading;
    else if (e.absolute !== false && typeof e.alpha === 'number') h = (360 - e.alpha) % 360;
    if (h == null) return;
    hasOri = true;
    // телефон вертикально: beta≈90 — камера на горизонт; більше — вгору
    const beta = e.beta || 90;
    const sOr = (screen.orientation && screen.orientation.angle) || window.orientation || 0;
    az = (h + sOr + 360) % 360;
    el = Math.max(-30, Math.min(89, beta - 90));
  }
  async function start() {
    $('#start').style.display = 'none';
    try {
      if (typeof DeviceOrientationEvent !== 'undefined' && DeviceOrientationEvent.requestPermission) await DeviceOrientationEvent.requestPermission();
    } catch (e) {}
    window.addEventListener('deviceorientationabsolute', onOri, true);
    window.addEventListener('deviceorientation', onOri, true);
    try {
      const st = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false });
      $('#cam').srcObject = st;
    } catch (e) { $('#sub').textContent = 'Камера недоступна — показую небо без фону'; }
    setTimeout(() => { if (!hasOri) $('#sub').textContent = 'Немає компаса — відкрийте на телефоні. Тут можна тягнути мишею.'; }, 2500);
  }
  $('#go').onclick = start;
  cv.addEventListener('pointerdown', e => drag = { x: e.clientX, y: e.clientY, az, el });
  addEventListener('pointerup', () => drag = null);
  addEventListener('pointermove', e => { if (!drag || hasOri) return; az = (drag.az - (e.clientX - drag.x) * HFOV / innerWidth + 360) % 360; el = Math.max(-20, Math.min(80, drag.el + (e.clientY - drag.y) * HFOV / innerWidth)); });

  function frame() {
    const W = cv.width = innerWidth * devicePixelRatio, H = cv.height = innerHeight * devicePixelRatio;
    const k = devicePixelRatio, hf = HFOV, vf = HFOV * H / W;
    cx.clearRect(0, 0, W, H);
    // горизонт
    const hy = H / 2 + el / vf * H;
    cx.strokeStyle = 'rgba(255,255,255,.25)'; cx.lineWidth = 1 * k; cx.beginPath(); cx.moveTo(0, hy); cx.lineTo(W, hy); cx.stroke();
    // компас унизу
    const by = H - 34 * k;
    cx.fillStyle = 'rgba(10,14,22,.55)'; cx.fillRect(0, by - 22 * k, W, 44 * k);
    cx.font = `700 ${13 * k}px Inter Tight, sans-serif`; cx.textAlign = 'center'; cx.textBaseline = 'middle';
    for (let a = 0; a < 360; a += 15) {
      let d = ((a - az + 540) % 360) - 180; if (Math.abs(d) > hf / 2 + 10) continue;
      const x = W / 2 + d / hf * W, lab = { 0: 'Пн', 90: 'Сх', 180: 'Пд', 270: 'Зх' }[a];
      cx.fillStyle = lab ? '#fff' : 'rgba(255,255,255,.4)';
      if (lab) cx.fillText(lab, x, by); else cx.fillRect(x - k, by - 5 * k, 2 * k, 10 * k);
    }
    cx.fillStyle = '#FF3B4E'; cx.fillRect(W / 2 - k, by - 20 * k, 2 * k, 8 * k);
    if (!SNAP || !home) { requestAnimationFrame(frame); return; }
    const serverT = Date.now() / 1000 + offset, Hm = xy(home);
    let best = null;
    for (const tr of SNAP.tracks) {
      if (tr.status !== 'active') continue;
      const p = posAt(tr, serverT), P = xy(p), d = dist(Hm, P);
      if (d > 150) continue;
      const tAz = brg(Hm, P), tEl = Math.atan2(ALT[tr.type] || 1.5, Math.max(0.3, d)) / D2R;
      const toward = tr.hd != null && angd(tr.hd, brg(P, Hm)) < 25, eta = toward ? d / tr.speed * 60 : null;
      if (eta != null && (!best || eta < best.eta)) best = { tr, d, eta, tAz };
      let dx = ((tAz - az + 540) % 360) - 180, dy = tEl - el;
      const x = W / 2 + dx / hf * W, y = H / 2 - dy / vf * H;
      const on = Math.abs(dx) < hf / 2 && y > 0 && y < H;
      // компасна мітка
      if (Math.abs(dx) < hf / 2 + 10) { cx.fillStyle = COL[tr.type]; cx.beginPath(); cx.arc(x, by - 14 * k, 4 * k, 0, 7); cx.fill(); }
      if (on) {
        const s = Math.max(28, Math.min(80, 900 / d)) * k;
        cx.save(); cx.translate(x, y);
        const g = cx.createRadialGradient(0, 0, 0, 0, 0, s * 1.3); g.addColorStop(0, COL[tr.type] + 'aa'); g.addColorStop(1, COL[tr.type] + '00');
        cx.fillStyle = g; cx.beginPath(); cx.arc(0, 0, s * 1.3, 0, 7); cx.fill();
        if (tr.hd != null) cx.rotate((((tr.hd - az + 540) % 360) - 180) * D2R); // ніс угору — летить від вас, донизу — на вас
        if (IMG[tr.type] && IMG[tr.type].complete) cx.drawImage(IMG[tr.type], -s / 2, -s / 2, s, s);
        cx.restore();
        cx.font = `800 ${15 * k}px Inter Tight, sans-serif`; cx.textAlign = 'left'; cx.lineWidth = 4 * k; cx.strokeStyle = 'rgba(0,0,0,.8)';
        const l1 = NAME[tr.type] + (tr.count > 1 ? ' ×' + tr.count : '') + ' · ' + Math.round(d) + ' км', l2 = (eta != null ? '~' + Math.max(1, Math.round(eta)) + ' хв до вас' : '') + (tr.next ? (eta != null ? ' · ' : '') + '→ ' + tr.next : '');
        cx.strokeText(l1, x + s * 0.7, y - 6 * k); cx.fillStyle = eta != null ? '#FF6B70' : '#fff'; cx.fillText(l1, x + s * 0.7, y - 6 * k);
        cx.font = `600 ${12 * k}px Inter Tight, sans-serif`; cx.strokeText(l2, x + s * 0.7, y + 12 * k); cx.fillStyle = '#C9D2E3'; cx.fillText(l2, x + s * 0.7, y + 12 * k);
      } else if (Math.abs(dx) >= hf / 2) { // стрілка повороту
        const left = dx < 0, ex = left ? 26 * k : W - 26 * k, ey = Math.max(90 * k, Math.min(H - 90 * k, y));
        cx.fillStyle = COL[tr.type]; cx.beginPath();
        if (left) { cx.moveTo(ex - 12 * k, ey); cx.lineTo(ex + 6 * k, ey - 10 * k); cx.lineTo(ex + 6 * k, ey + 10 * k); }
        else { cx.moveTo(ex + 12 * k, ey); cx.lineTo(ex - 6 * k, ey - 10 * k); cx.lineTo(ex - 6 * k, ey + 10 * k); }
        cx.fill(); cx.font = `700 ${11 * k}px Inter Tight, sans-serif`; cx.textAlign = left ? 'left' : 'right'; cx.fillStyle = '#fff';
        cx.fillText(Math.round(d) + ' км', left ? ex + 10 * k : ex - 10 * k, ey + 22 * k);
      }
    }
    $('#head').textContent = best ? NAME[best.tr.type] + ' · ' + Math.round(best.d) + ' км · ~' + Math.max(1, Math.round(best.eta)) + ' хв' : 'Небо над вами чисте';
    $('#sub').textContent = best ? 'Іде на вас з ' + ['півночі', 'північного сходу', 'сходу', 'південного сходу', 'півдня', 'південного заходу', 'заходу', 'північного заходу'][Math.round(best.tAz / 45) % 8] + ' — в укриття' : (hasOri ? 'Цілей, що йдуть на вас, немає' : $('#sub').textContent);
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})();
