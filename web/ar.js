// «Небо в камері»: де відносно вас зараз цілі — азимут, кут над горизонтом, курс на 5 хв уперед і хвилини до вас.
(() => {
  'use strict';
  const $ = s => document.querySelector(s);
  const D2R = Math.PI / 180, KX = 111.32 * Math.cos(49 * D2R), KY = 110.57;
  const xy = ([lon, lat]) => [(lon - 31.5) * KX, (lat - 49) * KY];
  const ll = ([x, y]) => [x / KX + 31.5, 49 + y / KY];
  const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
  const brg = (a, b) => (Math.atan2(b[0] - a[0], b[1] - a[1]) / D2R + 360) % 360;
  const angd = (a, b) => { let d = Math.abs(a - b) % 360; return d > 180 ? 360 - d : d; };
  const wrap = d => ((d + 540) % 360) - 180;
  const NAME = { shahed: 'Шахед', jet: 'Реактивний БпЛА', molniya: '«Молнія»', cruise: 'Крилата ракета', ballistic: 'Балістика' };
  const ALT = { shahed: 1.5, molniya: 0.8, jet: 3, cruise: 0.15, ballistic: 20 };   // типові висоти, км
  const COL = { shahed: '#FF9F2E', jet: '#FF5FA2', molniya: '#FFD84A', cruise: '#FF4B3E', ballistic: '#C77DFF' };
  const SIDE = ['півночі', 'північного сходу', 'сходу', 'південного сходу', 'півдня', 'південного заходу', 'заходу', 'північного заходу'];
  const HFOV = 62; // горизонтальний кут камери телефона в портреті, °
  const cv = $('#ov'), cx = cv.getContext('2d');
  let SNAP = null, offset = 0, home = null, hasOri = false, drag = null, calib = false, lastBuzz = 0, wake = null;
  // згладжений напрям камери: азимут — через вектор (щоб 359°→0° не «стрибав»), кут, крен
  const cam = { sx: 0, sy: 1, el: 15, roll: 0, raw: null };
  let azOffset = +(localStorage.getItem('ar-offset') || 0);
  const IMG = {};
  for (const t of Object.keys(NAME)) { const i = new Image(); i.src = 'sprites/t-' + t + '.png'; IMG[t] = i; }
  try { home = JSON.parse(localStorage.getItem('home') || 'null'); } catch (e) {}

  function posAt(tr, serverT) { // та сама екстраполяція, що й на карті
    if (tr.status !== 'active') return [tr.lon, tr.lat];
    let km = tr.speed * Math.max(0, serverT - tr.ts) / 3600;
    const pts = [xy([tr.lon, tr.lat]), ...(tr.route || []).map(xy)];
    if (pts.length === 1) { if (tr.hd == null) return [tr.lon, tr.lat]; km = Math.min(km, tr.speed * 4 / 60); const r = tr.hd * D2R; return ll([pts[0][0] + Math.sin(r) * km, pts[0][1] + Math.cos(r) * km]); }
    let acc = 0; for (let i = 1; i < pts.length; i++) { const d = dist(pts[i - 1], pts[i]); if (acc + d >= km) { const f = (km - acc) / (d || 1); return ll([pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * f, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * f]); } acc += d; }
    return ll(pts[pts.length - 1]);
  }
  function load() { fetch('/api/state').then(r => r.json()).then(s => { SNAP = s; offset = s.now - Date.now() / 1000; }).catch(() => {}); }
  load(); setInterval(load, 2500);

  /* ---------- орієнтація: повна матриця W3C (z-x'-y''), вектор задньої камери = −Z пристрою ---------- */
  function onOri(e) {
    if (e.beta == null) return;
    let alpha = e.alpha;
    if (typeof e.webkitCompassHeading === 'number') alpha = 360 - e.webkitCompassHeading;      // iOS: абсолютний компас
    else if (e.type === 'deviceorientation' && e.absolute !== true && gotAbsolute) return;     // Android: беремо абсолютну подію
    if (alpha == null) return;
    hasOri = true;
    const a = alpha * D2R, b = e.beta * D2R, g = (e.gamma || 0) * D2R;
    const ca = Math.cos(a), sa = Math.sin(a), cb = Math.cos(b), sb = Math.sin(b), cg = Math.cos(g), sg = Math.sin(g);
    const vx = -ca * sg - sa * sb * cg, vy = -sa * sg + ca * sb * cg, vz = -cb * cg;   // куди дивиться камера (схід, північ, вгору)
    const rz = -cb * sg, uz = sb;                                                       // крен: «праве» й «верхнє» відносно горизонту
    const sOr = ((screen.orientation && screen.orientation.angle) || window.orientation || 0);
    let az = Math.atan2(vx, vy) / D2R;
    const el = Math.asin(Math.max(-1, Math.min(1, vz))) / D2R;
    let roll = Math.atan2(rz, uz) / D2R - sOr;
    cam.raw = { az: az + azOffset, el, roll };
  }
  let gotAbsolute = false;
  window.addEventListener('deviceorientationabsolute', e => { gotAbsolute = true; onOri(e); }, true);
  window.addEventListener('deviceorientation', onOri, true);

  function smooth() { // низькочастотний фільтр — без тремтіння
    if (!cam.raw) return;
    const k = 0.18, r = cam.raw;
    cam.sx += (Math.sin(r.az * D2R) - cam.sx) * k; cam.sy += (Math.cos(r.az * D2R) - cam.sy) * k;
    cam.el += (r.el - cam.el) * k; cam.roll += wrap(r.roll - cam.roll) * k;
  }
  const azNow = () => (Math.atan2(cam.sx, cam.sy) / D2R + 360) % 360;

  async function start() {
    $('#start').style.display = 'none';
    try { if (typeof DeviceOrientationEvent !== 'undefined' && DeviceOrientationEvent.requestPermission) await DeviceOrientationEvent.requestPermission(); } catch (e) {}
    try { const st = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false }); $('#cam').srcObject = st; }
    catch (e) { $('#sub').textContent = location.protocol === 'https:' || location.hostname === 'localhost' ? 'Камера недоступна — показую небо без фону' : 'Камері потрібне https — відкрийте адресу з phone.bat'; }
    try { wake = await navigator.wakeLock.request('screen'); } catch (e) {}
    if (!home && navigator.geolocation) navigator.geolocation.getCurrentPosition(p => { home = [p.coords.longitude, p.coords.latitude]; localStorage.setItem('home', JSON.stringify(home)); }, () => { $('#sub').textContent = 'Потрібне ваше місце — позначте дім у «Тривозі»'; });
    setTimeout(() => { if (!hasOri) $('#sub').textContent = 'Немає компаса — відкрийте на телефоні. Тут небо можна тягнути мишею.'; }, 2500);
  }
  $('#go').onclick = start;
  document.addEventListener('visibilitychange', async () => { if (document.visibilityState === 'visible' && wake) try { wake = await navigator.wakeLock.request('screen'); } catch (e) {} });
  // калібрування: компаси телефонів часто брешуть на 10–30° — підлаштовуємо пальцем по видимому орієнтиру
  $('#cal').onclick = () => { calib = !calib; $('#cal').classList.toggle('on', calib); $('#cal').textContent = calib ? 'Готово' : 'Підлаштувати компас'; if (!calib) localStorage.setItem('ar-offset', String(azOffset)); };
  cv.addEventListener('pointerdown', e => drag = { x: e.clientX, y: e.clientY, az: azNow(), el: cam.el, off: azOffset });
  addEventListener('pointerup', () => drag = null);
  addEventListener('pointermove', e => {
    if (!drag) return;
    const dAz = -(e.clientX - drag.x) * HFOV / innerWidth;
    if (calib && hasOri) { azOffset = drag.off + dAz; return; }
    if (hasOri) return;
    const az = (drag.az + dAz + 360) % 360; cam.sx = Math.sin(az * D2R); cam.sy = Math.cos(az * D2R);
    cam.el = Math.max(-20, Math.min(80, drag.el + (e.clientY - drag.y) * HFOV / innerWidth));
  });

  function frame() {
    smooth();
    const k = devicePixelRatio, W = cv.width = innerWidth * k, H = cv.height = innerHeight * k;
    const hf = HFOV, vf = HFOV * H / W, az = azNow(), el = cam.el;
    cx.clearRect(0, 0, W, H);
    const proj = (tAz, tEl) => [W / 2 + wrap(tAz - az) / hf * W, H / 2 - (tEl - el) / vf * H];
    // світ (горизонт, цілі) крутимо проти крену телефона, компас — ні
    cx.save(); cx.translate(W / 2, H / 2); cx.rotate(cam.roll * D2R); cx.translate(-W / 2, -H / 2);
    const hy = H / 2 + el / vf * H;
    // земля трохи темніша, горизонт — тонка світла лінія з легким сяйвом
    cx.fillStyle = 'rgba(0,0,0,.28)'; cx.fillRect(-W, hy, W * 3, H * 2);
    cx.shadowColor = 'rgba(140,180,255,.9)'; cx.shadowBlur = 10 * k;
    cx.strokeStyle = 'rgba(200,220,255,.7)'; cx.lineWidth = 1.2 * k; cx.beginPath(); cx.moveTo(-W, hy); cx.lineTo(2 * W, hy); cx.stroke(); cx.shadowBlur = 0;
    // сторони світу на горизонті
    cx.font = `700 ${12 * k}px Inter Tight, sans-serif`; cx.textAlign = 'center'; cx.fillStyle = 'rgba(255,255,255,.75)';
    for (const [a, n] of [[0, 'ПІВНІЧ'], [90, 'СХІД'], [180, 'ПІВДЕНЬ'], [270, 'ЗАХІД']]) { const [x] = proj(a, 0); if (x > -50 && x < W + 50) cx.fillText(n, x, hy - 8 * k); }
    // приціл
    cx.strokeStyle = 'rgba(255,255,255,.5)'; cx.lineWidth = 1.5 * k; cx.beginPath(); cx.arc(W / 2, H / 2, 22 * k, 0, 7); cx.stroke();

    const by = H - 34 * k, marks = [];
    let best = null, aimed = false;
    if (SNAP && home) {
      const serverT = Date.now() / 1000 + offset, Hm = xy(home);
      const list = [];
      for (const tr of SNAP.tracks) {
        if (tr.status !== 'active') continue;
        const p = posAt(tr, serverT), P = xy(p), d = dist(Hm, P);
        if (d > 150) continue;
        const tAz = brg(Hm, P), alt = ALT[tr.type] || 1.5, tEl = Math.atan2(alt, Math.max(0.3, d)) / D2R;
        const toward = tr.hd != null && angd(tr.hd, brg(P, Hm)) < 25, eta = toward && tr.conf >= 0.5 ? d / tr.speed * 60 : null;
        if (eta != null && eta <= 45 && (!best || eta < best.eta)) best = { tr, d, eta, tAz, tEl };
        list.push({ tr, p, d, tAz, tEl, eta, alt });
        marks.push({ tAz, c: COL[tr.type], thr: eta != null });
      }
      list.sort((a, b) => b.d - a.d); // ближчі — поверх
      const boxes = []; // підписи не налазять: пріоритет — загрози й ближчі
      const prio = list.slice().sort((a, b) => (a.eta == null) - (b.eta == null) || a.d - b.d);
      const showLabel = new Set();
      for (const o of prio) { const [x, y] = proj(o.tAz, o.tEl); const s = Math.max(30, Math.min(96, 1100 / o.d)) * k;
        const bx = [x + s * 0.6, y - 22 * k, x + s * 0.6 + 230 * k, y + 20 * k];
        if (!boxes.some(b => bx[0] < b[2] && bx[2] > b[0] && bx[1] < b[3] && bx[3] > b[1])) { boxes.push(bx); showLabel.add(o); } }
      for (const o of list) {
        const { tr, d, tAz, tEl, eta } = o;
        const [x, y] = proj(tAz, tEl);
        const on = x > -40 && x < W + 40 && y > -40 && y < H + 40;
        if (!on) continue;
        const fade = Math.max(0.35, 1 - d / 170), s = Math.max(30, Math.min(96, 1100 / d)) * k, c = COL[tr.type];
        // курс на 5 хв уперед — лінія в небі
        if (tr.hd != null || (tr.route || []).length) {
          cx.strokeStyle = c; cx.lineWidth = 2 * k; cx.setLineDash([6 * k, 6 * k]); cx.globalAlpha = 0.8 * fade; cx.beginPath();
          let first = true;
          for (let m = 0; m <= 5; m++) {
            const q = posAt(Object.assign({}, tr), Date.now() / 1000 + offset + m * 60), Q = xy(q), dq = dist(xy(home), Q);
            const [qx, qy] = proj(brg(xy(home), Q), Math.atan2(o.alt, Math.max(0.3, dq)) / D2R);
            first ? cx.moveTo(qx, qy) : cx.lineTo(qx, qy); first = false;
          }
          cx.stroke(); cx.setLineDash([]); cx.globalAlpha = 1;
        }
        // ореол і силует (ніс угору — від вас, донизу — на вас)
        cx.save(); cx.translate(x, y); cx.globalAlpha = fade;
        const g = cx.createRadialGradient(0, 0, 0, 0, 0, s * 1.2); g.addColorStop(0, (eta != null ? '#FF3B4E' : c) + 'cc'); g.addColorStop(1, c + '00');
        cx.fillStyle = g; cx.beginPath(); cx.arc(0, 0, s * 1.2, 0, 7); cx.fill();
        if (eta != null) { const ph = (performance.now() / 900) % 1; cx.strokeStyle = `rgba(255,59,78,${1 - ph})`; cx.lineWidth = 2 * k; cx.beginPath(); cx.arc(0, 0, s * (0.6 + ph), 0, 7); cx.stroke(); }
        if (tr.hd != null) cx.rotate(wrap(tr.hd - az) * D2R);
        if (IMG[tr.type] && IMG[tr.type].complete) cx.drawImage(IMG[tr.type], -s / 2, -s / 2, s, s);
        cx.restore(); cx.globalAlpha = 1;
        // підпис
        if (!showLabel.has(o)) { if (best && tr === best.tr && Math.hypot(x - W / 2, y - H / 2) < 60 * k) aimed = true; continue; }
        cx.textAlign = 'left'; cx.lineJoin = 'round'; cx.lineWidth = 5 * k; cx.strokeStyle = 'rgba(0,0,0,.85)';
        const l1 = NAME[tr.type] + (tr.count > 1 ? ' ×' + tr.count : '') + ' · ' + Math.round(d) + ' км';
        const l2 = (eta != null ? '~' + Math.max(1, Math.round(eta)) + ' хв до вас' : (tr.hd != null ? 'не на вас' : 'курс невідомий')) + (tr.next ? ' · → ' + tr.next : '');
        cx.font = `800 ${15 * k}px Inter Tight, sans-serif`; cx.strokeText(l1, x + s * 0.65, y - 5 * k); cx.fillStyle = eta != null ? '#FF6B70' : '#fff'; cx.fillText(l1, x + s * 0.65, y - 5 * k);
        cx.font = `600 ${12 * k}px Inter Tight, sans-serif`; cx.strokeText(l2, x + s * 0.65, y + 13 * k); cx.fillStyle = '#C9D2E3'; cx.fillText(l2, x + s * 0.65, y + 13 * k);
        if (best && tr === best.tr && Math.hypot(x - W / 2, y - H / 2) < 60 * k) aimed = true;
      }
    }
    cx.restore();

    // загроза поза кадром — велика червона стрілка
    if (best) {
      const dx = wrap(best.tAz - az);
      if (Math.abs(dx) > hf / 2 - 4) {
        const left = dx < 0, ex = left ? 34 * k : W - 34 * k, ey = H / 2;
        cx.fillStyle = '#FF3B4E'; cx.shadowColor = '#FF3B4E'; cx.shadowBlur = 20 * k; cx.beginPath();
        if (left) { cx.moveTo(ex - 18 * k, ey); cx.lineTo(ex + 10 * k, ey - 18 * k); cx.lineTo(ex + 10 * k, ey + 18 * k); }
        else { cx.moveTo(ex + 18 * k, ey); cx.lineTo(ex - 10 * k, ey - 18 * k); cx.lineTo(ex - 10 * k, ey + 18 * k); }
        cx.fill(); cx.shadowBlur = 0;
        cx.font = `800 ${13 * k}px Inter Tight, sans-serif`; cx.textAlign = left ? 'left' : 'right'; cx.fillStyle = '#fff';
        cx.fillText('загроза ' + Math.round(Math.abs(dx)) + '° ' + (left ? 'ліворуч' : 'праворуч'), left ? ex + 16 * k : ex - 16 * k, ey + 34 * k);
      }
      if (aimed && Date.now() - lastBuzz > 1500 && navigator.vibrate) { navigator.vibrate(40); lastBuzz = Date.now(); }
    }
    // компасна стрічка
    cx.fillStyle = 'rgba(10,14,22,.6)'; cx.fillRect(0, by - 22 * k, W, 44 * k);
    cx.font = `700 ${13 * k}px Inter Tight, sans-serif`; cx.textAlign = 'center'; cx.textBaseline = 'middle';
    for (let a = 0; a < 360; a += 15) {
      const d = wrap(a - az); if (Math.abs(d) > hf / 2 + 10) continue;
      const x = W / 2 + d / hf * W, lab = { 0: 'Пн', 45: 'ПнСх', 90: 'Сх', 135: 'ПдСх', 180: 'Пд', 225: 'ПдЗх', 270: 'Зх', 315: 'ПнЗх' }[a];
      cx.fillStyle = lab ? '#fff' : 'rgba(255,255,255,.4)';
      if (lab) cx.fillText(lab, x, by); else cx.fillRect(x - k, by - 5 * k, 2 * k, 10 * k);
    }
    for (const m of marks) { const d = wrap(m.tAz - az); if (Math.abs(d) > hf / 2 + 10) continue; const x = W / 2 + d / hf * W; cx.fillStyle = m.thr ? '#FF3B4E' : m.c; cx.beginPath(); cx.arc(x, by - 15 * k, (m.thr ? 5 : 3.5) * k, 0, 7); cx.fill(); }
    cx.fillStyle = '#FF3B4E'; cx.fillRect(W / 2 - k, by - 21 * k, 2 * k, 9 * k);
    cx.textBaseline = 'alphabetic';

    // шапка
    if (best) { $('#head').textContent = NAME[best.tr.type] + ' · ' + Math.round(best.d) + ' км · ~' + Math.max(1, Math.round(best.eta)) + ' хв'; $('#sub').textContent = 'Іде на вас з ' + SIDE[Math.round(best.tAz / 45) % 8] + ' — в укриття'; $('.card').classList.add('danger'); }
    else if (SNAP && home) { $('#head').textContent = 'Небо над вами чисте'; if (hasOri || calib) $('#sub').textContent = calib ? 'Тягніть, щоб сторони світу збіглися з реальними' : 'Цілей, що йдуть на вас, немає'; $('.card').classList.remove('danger'); }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})();
