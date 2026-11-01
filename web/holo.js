/* «Голостіл» — експериментальний режим: екран як вікно в об'ємний макет карти.
   Голова (вебкамера, MediaPipe Face Landmarker) рухає точку спостереження — камера карти облітає центр макета.
   Руки (MediaPipe Hand Landmarker): зведені великий і вказівний = «захопити»; одна рука тягне макет,
   дві руки із захопленням — масштаб і поворот. На телефоні без камери — нахил телефона (гіроскоп).
   Відео обробляється лише в браузері: кадри нікуди не надсилаються й не записуються. */
(function () {
  'use strict';
  const MP = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14';
  const FACE = 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task';
  const HAND = 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task';
  const $ = s => document.querySelector(s);
  const mobile = matchMedia('(pointer:coarse)').matches;
  const H = {
    on: false, mode: null, stream: null, video: null, face: null, hands: null, raf: 0,
    base: null,                 // калібрування: положення голови «по центру»
    head: { x: 0, y: 0, z: 0, ok: false, seen: 0 }, applied: { b: 0, p: 0, z: 0 },
    grab: [], cool: 0, two: null, lastT: 0,
  };
  const map = () => window.FxLayer && window.FxLayer.map;
  const say = m => { const t = $('#toast'); if (!t) return; t.textContent = m; t.hidden = false; clearTimeout(say.h); say.h = setTimeout(() => t.hidden = true, 2600); };
  // згладжування без тремтіння: швидко йде за великим рухом, гасить дрібний шум (спрощений One Euro)
  function smooth(prev, v, dt, minCut, beta) {
    if (prev == null) return v;
    const dv = Math.abs(v - prev) / Math.max(dt, 1e-3), cut = minCut + beta * dv;
    const a = 1 / (1 + 1 / (2 * Math.PI * cut * dt));
    return prev + a * (v - prev);
  }

  /* ---------------- інтерфейс ---------------- */
  function ui() {
    if ($('#holo-hud')) return;
    const d = document.createElement('div'); d.id = 'holo-hud'; d.className = 'holo-hud';
    d.innerHTML = '<video id="holo-v" playsinline muted></video><div class="hh-txt"><b>Голостіл</b><span id="holo-st">запуск…</span></div>' +
      '<div class="hh-btn"><button id="holo-c">Центрувати</button><button id="holo-x" title="Вимкнути камеру й режим">✕</button></div>';
    document.body.appendChild(d);
    for (let i = 0; i < 2; i++) { const c = document.createElement('div'); c.className = 'holo-cur'; c.id = 'holo-cur' + i; c.hidden = true; c.innerHTML = '<i></i><span>Захоплено</span>'; document.body.appendChild(c); }
    $('#holo-c').onclick = () => { H.base = null; say('Сядьте рівно — центрую'); };
    $('#holo-x').onclick = () => { stop(); const cb = $('#st-holo'); if (cb) cb.checked = false; save(false); };
  }
  function status(t) { const s = $('#holo-st'); if (s) s.textContent = t; }
  function save(on) { try { const p = JSON.parse(localStorage.getItem('pref') || '{}'); p.holo = on; p.holoMode = H.mode; localStorage.setItem('pref', JSON.stringify(p)); } catch (e) {} }

  /* ---------------- запуск / зупинка ---------------- */
  async function start(mode) {
    if (H.on) stop();
    H.mode = mode || (mobile ? 'tilt' : 'cam'); H.on = true; H.base = null; H.applied = { b: 0, p: 0, z: 0 };
    ui(); document.body.classList.add('holo-on');
    const m = map(); if (m && m.getPitch() < 35) m.easeTo({ pitch: 52, duration: 900 });
    if (H.mode === 'tilt') return startTilt();
    try {
      status('камера…');
      H.stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } }, audio: false });
    } catch (e) {
      status('камера недоступна');
      say(location.protocol === 'https:' || location.hostname === 'localhost' ? 'Без доступу до камери — вмикаю керування нахилом' : 'Камера працює лише через https (на телефоні — адреса з :8443)');
      if (mobile) return startTilt();
      return;
    }
    H.video = $('#holo-v'); H.video.srcObject = H.stream; await H.video.play().catch(() => {});
    status('завантажую моделі…');
    try {
      const vis = await import(MP + '/vision_bundle.mjs');
      const fs = await vis.FilesetResolver.forVisionTasks(MP + '/wasm');
      const opt = d => ({ baseOptions: { modelAssetPath: d, delegate: 'GPU' }, runningMode: 'VIDEO' });
      H.face = await vis.FaceLandmarker.createFromOptions(fs, Object.assign(opt(FACE), { numFaces: 1 }));
      H.hands = await vis.HandLandmarker.createFromOptions(fs, Object.assign(opt(HAND), { numHands: 2 }));
    } catch (e) {
      console.warn('holo', e); status('не вдалося завантажити моделі'); say('Моделі MediaPipe не завантажились (потрібен інтернет)'); return;
    }
    if (!H.on) return;
    status('дивіться в екран'); loop();
  }
  function stop() {
    H.on = false; cancelAnimationFrame(H.raf);
    if (H.stream) H.stream.getTracks().forEach(t => t.stop());   // камера справді вимикається
    H.stream = null; if (H.video) H.video.srcObject = null;
    try { H.face && H.face.close(); H.hands && H.hands.close(); } catch (e) {}
    H.face = H.hands = null;
    window.removeEventListener('deviceorientation', onTilt);
    unapply(); document.body.classList.remove('holo-on');
    const d = $('#holo-hud'); if (d) d.remove(); document.querySelectorAll('.holo-cur').forEach(c => c.remove());
  }

  /* ---------------- точка спостереження ---------------- */
  // різниця «треба − вже застосовано» додається до поточної камери, тож миша й пальці працюють як завжди
  function apply(hx, hy, hz) {
    const m = map(); if (!m) return;
    const want = { b: -hx * 28, p: -hy * 22, z: hz * 0.9 };
    const db = want.b - H.applied.b, dp = want.p - H.applied.p, dz = want.z - H.applied.z;
    if (Math.abs(db) + Math.abs(dp) + Math.abs(dz) < 0.02) return;
    m.jumpTo({ bearing: m.getBearing() + db, pitch: Math.max(0, Math.min(72, m.getPitch() + dp)), zoom: m.getZoom() + dz });
    H.applied = want;
  }
  function unapply() { const a = H.applied, m = map(); if (m && (a.b || a.p || a.z)) m.easeTo({ bearing: m.getBearing() - a.b, pitch: Math.max(0, m.getPitch() - a.p), zoom: m.getZoom() - a.z, duration: 600 }); H.applied = { b: 0, p: 0, z: 0 }; }

  /* ---------------- камера: голова + руки ---------------- */
  function loop() {
    if (!H.on) return;
    H.raf = requestAnimationFrame(loop);
    const v = H.video; if (!v || v.readyState < 2) return;
    const now = performance.now(); if (now - H.lastT < (mobile ? 50 : 30)) return;
    const dt = (now - (H.lastT || now)) / 1000 || 0.03; H.lastT = now;
    let fr = null, hr = null;
    try { fr = H.face.detectForVideo(v, now); if (!mobile || (H.tick = !H.tick)) hr = H.hands.detectForVideo(v, now + 0.1); } catch (e) { return; }
    // голова: середина між очима; відстань — за міжочною відстанню (оцінка приблизна)
    const lm = fr && fr.faceLandmarks && fr.faceLandmarks[0];
    if (lm) {
      const L = lm[33], R = lm[263];
      const cx = 1 - (L.x + R.x) / 2, cy = (L.y + R.y) / 2, iod = Math.hypot(L.x - R.x, L.y - R.y);
      if (!H.base) { H.base = { x: cx, y: cy, s: iod }; status('голова ✓ · руки: зведіть пальці, щоб захопити'); }
      const k = 1 / Math.max(0.05, H.base.s * 4);           // нормуємо рух на розмір обличчя
      const tx = (cx - H.base.x) * k * 2.2, ty = (cy - H.base.y) * k * 2.2, tz = Math.log2(iod / H.base.s);
      const dz = (a, w) => Math.sign(a) * Math.max(0, Math.abs(a) - w); // мертва зона: нерухома голова — нерухома сцена
      H.head.x = smooth(H.head.x, Math.max(-1, Math.min(1, dz(tx, 0.03))), dt, 1.0, 1.5);
      H.head.y = smooth(H.head.y, Math.max(-1, Math.min(1, dz(ty, 0.03))), dt, 1.0, 1.5);
      H.head.z = smooth(H.head.z, Math.max(-0.8, Math.min(0.8, dz(tz, 0.06))), dt, 0.6, 0.8);
      H.head.seen = now;
    } else if (now - H.head.seen > 600) { // обличчя зникло — плавно до нейтрального вигляду
      H.head.x *= 0.92; H.head.y *= 0.92; H.head.z *= 0.92;
    }
    apply(H.head.x, H.head.y, H.head.z);
    hands(hr, now);
  }

  function hands(hr, now) {
    const list = (hr && hr.landmarks) || [], W = innerWidth, Hh = innerHeight;
    const cur = [];
    list.slice(0, 2).forEach((p, i) => {
      const size = Math.hypot(p[0].x - p[9].x, p[0].y - p[9].y) || 0.1;
      const pin = Math.hypot(p[4].x - p[8].x, p[4].y - p[8].y) / size;
      const prev = H.grab[i] || {};
      const pinched = prev.pinched ? pin < 0.5 : pin < 0.32 && now > H.cool;   // гістерезис: не «мерехтить»
      const x = (1 - (p[4].x + p[8].x) / 2) * W, y = ((p[4].y + p[8].y) / 2) * Hh;
      const sx = prev.sx == null ? x : prev.sx + (x - prev.sx) * 0.45, sy = prev.sy == null ? y : prev.sy + (y - prev.sy) * 0.45;
      cur.push({ pinched, sx, sy, px: prev.sx, py: prev.sy, was: prev.pinched });
      if (prev.pinched && !pinched) H.cool = now + 250;      // після відпускання коротка пауза
    });
    // курсори
    for (let i = 0; i < 2; i++) { const c = $('#holo-cur' + i); if (!c) continue; const h = cur[i];
      c.hidden = !h; if (h) { c.style.transform = `translate(${h.sx}px,${h.sy}px)`; c.classList.toggle('pin', h.pinched); } }
    const m = map(); if (!m) { H.grab = cur; return; }
    const pins = cur.filter(h => h.pinched);
    if (pins.length === 2) { // дві руки: масштаб і поворот
      const d = Math.hypot(pins[0].sx - pins[1].sx, pins[0].sy - pins[1].sy), a = Math.atan2(pins[1].sy - pins[0].sy, pins[1].sx - pins[0].sx);
      if (H.two && pins.every(h => h.was)) {
        const dz = Math.log2(d / H.two.d), da = (a - H.two.a) * 180 / Math.PI;
        m.jumpTo({ zoom: m.getZoom() + dz, bearing: m.getBearing() - (Math.abs(da) < 40 ? da : 0) });
      }
      H.two = { d, a };
    } else {
      H.two = null;
      if (pins.length === 1) { const h = pins[0]; if (h.was && h.px != null) m.panBy([-(h.sx - h.px) * 1.6, -(h.sy - h.py) * 1.6], { duration: 0 }); }
    }
    H.grab = cur;
  }

  /* ---------------- телефон: нахил ---------------- */
  async function startTilt() {
    H.mode = 'tilt';
    try { if (typeof DeviceOrientationEvent !== 'undefined' && DeviceOrientationEvent.requestPermission) { const r = await DeviceOrientationEvent.requestPermission(); if (r !== 'granted') throw 0; } }
    catch (e) { status('немає доступу до гіроскопа'); return; }
    window.addEventListener('deviceorientation', onTilt);
    status('нахиляйте телефон · «Центрувати» — нове положення');
  }
  function onTilt(e) {
    if (!H.on || e.beta == null) return;
    if (!H.base) H.base = { b: e.beta, g: e.gamma };
    const now = performance.now(), dt = (now - (H.lastT || now)) / 1000 || 0.03; H.lastT = now;
    const tx = Math.max(-1, Math.min(1, (e.gamma - H.base.g) / 30)), ty = Math.max(-1, Math.min(1, (e.beta - H.base.b) / 30));
    H.head.x = smooth(H.head.x, tx, dt, 1.2, 0.8); H.head.y = smooth(H.head.y, -ty, dt, 1.2, 0.8);
    apply(H.head.x, H.head.y, 0);
  }

  /* ---------------- налаштування ---------------- */
  function bind() {
    const cb = $('#st-holo'); if (!cb) return;
    let p = {}; try { p = JSON.parse(localStorage.getItem('pref') || '{}'); } catch (e) {}
    const seg = $('#st-holo-mode');
    H.mode = p.holoMode || (mobile ? 'tilt' : 'cam');
    if (seg) { seg.querySelectorAll('button').forEach(b => { b.classList.toggle('on', b.dataset.v === H.mode);
      b.onclick = () => { H.mode = b.dataset.v; seg.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b)); save(cb.checked); if (cb.checked) start(H.mode); }; }); }
    cb.checked = false; // камеру ніколи не вмикаємо самі після перезавантаження — лише за дією людини
    cb.onchange = () => { save(cb.checked); if (cb.checked) start(H.mode); else stop(); };
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind); else bind();
  window.Holo = { start, stop };
})();
