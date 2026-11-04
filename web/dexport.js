/* Мапа доби: експорт PDF (A4, з лого) і короткого відео (4:5, з лого) — 04.11.
   Мапу на час експорту рендеримо у фіксованому розмірі, щоб результат був однаковий з телефона і з комп'ютера.
   Користується глобальними map, D, DAY, OBL, VB, VS, T, ORDER, MAJOR, draw, bounds, OBLN, fd, hm з daily.html. */
(function () {
  'use strict';
  const FONT = 'Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif';
  const BLUE = '#3B8BFF', GOLD = '#F2A93B', MUTE = '#8C97AB';
  const SITE = 'sky.navryx.com.ua';
  let busy = false, LOGO = null;
  const img = src => new Promise(ok => { const i = new Image(); i.onload = () => ok(i); i.onerror = () => ok(null); i.src = src; });
  const script = src => new Promise((ok, no) => { const e = document.createElement('script'); e.src = src; e.onload = ok; e.onerror = no; document.head.appendChild(e); });
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const fname = ext => 'navryx-sky-doba-' + DAY + (OBL ? '-' + OBL.toLowerCase().replace(/[^a-zа-яіїєґ]+/gi, '') : '') + '.' + ext;

  const st = document.createElement('style');
  st.textContent = `#xveil{position:fixed;inset:0;z-index:50;background:rgba(5,7,11,.92);display:grid;place-items:center;padding:16px;color:#F2F5FA;font-family:${FONT}}
  #xveil .xb{max-width:440px;width:100%;text-align:center}#xveil .xt{font-weight:700;margin-top:14px}#xveil .xm{color:${MUTE};font-size:13px;margin-top:6px}
  #xveil .bar{height:6px;border-radius:4px;background:rgba(255,255,255,.1);margin-top:14px;overflow:hidden}#xveil .bar i{display:block;height:100%;width:0;background:linear-gradient(90deg,${GOLD},${BLUE})}
  #xveil .pv{max-width:100%;max-height:55vh;border-radius:14px;box-shadow:0 10px 40px rgba(0,0,0,.6)}
  #xveil .acts{display:flex;gap:8px;justify-content:center;margin-top:14px;flex-wrap:wrap}
  #xveil .acts a,#xveil .acts button{border:0;border-radius:12px;padding:10px 16px;font:700 14px ${FONT};color:#fff;background:rgba(255,255,255,.12);text-decoration:none;cursor:pointer}
  #xveil .acts .pri{background:${BLUE}}#xveil .logo{width:64px;height:64px}`;
  document.head.appendChild(st);

  function veil(html) { let v = document.getElementById('xveil'); if (!v) { v = document.createElement('div'); v.id = 'xveil'; document.body.appendChild(v); } v.innerHTML = '<div class="xb">' + html + '</div>'; return v; }
  function unveil() { const v = document.getElementById('xveil'); if (v) v.remove(); }
  function ready(blob, name, kind, preview) {
    const url = URL.createObjectURL(blob), file = new File([blob], name, { type: blob.type });
    const canShare = navigator.canShare && navigator.canShare({ files: [file] });
    const v = veil((preview || '') + '<div class="xt">' + (kind === 'pdf' ? 'PDF готовий' : 'Відео готове') + '</div>' +
      '<div class="acts">' + (canShare ? '<button class="pri" id="xsh">Поділитися</button>' : '') +
      '<a ' + (canShare ? '' : 'class="pri" ') + 'href="' + url + '" download="' + name + '">Зберегти</a><button id="xcl">Закрити</button></div>');
    const pv = v.querySelector('video'); if (pv) pv.src = url;
    v.querySelector('#xcl').onclick = () => { unveil(); setTimeout(() => URL.revokeObjectURL(url), 60000); };
    const sh = v.querySelector('#xsh');
    if (sh) sh.onclick = async () => { try { await navigator.share({ files: [file], title: 'NAVRYX SKY · Мапа доби' }); } catch (e) {} };
  }

  // фіксований кадр мапи: W×H css-пікселів, щільність pr; повертає функцію відновлення
  async function stage(W, H, pr) {
    const el = document.getElementById('map');
    const cam = { center: map.getCenter(), zoom: map.getZoom(), bearing: map.getBearing(), pitch: map.getPitch() };
    const oldPr = map.getPixelRatio ? map.getPixelRatio() : devicePixelRatio, cur = CUR;
    if (playing) { playing = false; document.getElementById('pl').textContent = '▶'; }
    map.stop(); XB = 1;
    Object.assign(el.style, { inset: 'auto', left: '0', top: '0', width: W + 'px', height: H + 'px' });
    if (map.setPixelRatio) map.setPixelRatio(pr);
    map.resize();
    map.jumpTo({ bearing: 0, pitch: 0 });
    map.fitBounds(bounds(), { padding: Math.round(Math.min(W, H) * (OBL ? 0.03 : 0.015)), duration: 0 });
    await idle();
    return async () => {
      el.style.cssText = ''; XB = 0;
      if (map.setPixelRatio) map.setPixelRatio(oldPr);
      map.resize(); map.jumpTo(cam); draw(cur);
    };
  }
  const idle = () => new Promise(r => { let done = false; const f = () => { if (!done) { done = true; r(); } }; map.once('idle', f); map.triggerRepaint(); setTimeout(f, 9000); });

  // спільне: шапка з лого
  function rr(g, x, y, w, h, r) { g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r); g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath(); }
  function brand(g, x, y, s) {// лого + NAVRYX SKY + слоган; s — висота лого
    if (LOGO) g.drawImage(LOGO, x, y, s, s);
    const tx = x + s + s * 0.18;
    g.textAlign = 'left'; g.textBaseline = 'alphabetic';
    g.font = '800 ' + Math.round(s * 0.36) + 'px ' + FONT; g.fillStyle = '#F2F5FA'; g.fillText('NAVRYX', tx, y + s * 0.5);
    const w = g.measureText('NAVRYX ').width; g.fillStyle = BLUE; g.fillText('SKY', tx + w, y + s * 0.5);
    g.font = '600 ' + Math.round(s * 0.17) + 'px ' + FONT; g.fillStyle = MUTE; g.fillText('Розумій, що відбувається в небі', tx, y + s * 0.8);
  }
  function grad(g, x, y, w, h) { const l = g.createLinearGradient(x, 0, x + w, 0); l.addColorStop(0, GOLD); l.addColorStop(1, BLUE); g.fillStyle = l; g.fillRect(x, y, w, h); }
  function cover(g, src, x, y, w, h) {// map canvas → прямокутник з обрізанням по центру
    const k = Math.max(w / src.width, h / src.height), sw = w / k, sh = h / k;
    g.drawImage(src, (src.width - sw) / 2, (src.height - sh) / 2, sw, sh, x, y, w, h);
  }
  function fit(g, t, maxW) { if (g.measureText(t).width <= maxW) return t; while (t.length > 1 && g.measureText(t + '…').width > maxW) t = t.slice(0, -1); return t + '…'; }
  function counts() { const c = {}; for (const t of D.tracks) if (t.inO) c[t.type] = (c[t.type] || 0) + 1; return ORDER.filter(k => T[k] && c[k]).map(k => [k, c[k]]); }
  const dateLine = () => fd(D.t0) + ' 09:00 – ' + fd(D.t1) + ' 09:00 ' + new Date(D.t1 * 1000).getFullYear();
  const nowStr = () => new Date().toLocaleString('uk-UA', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });

  // ---------- PDF ----------
  async function pdf() {
    if (busy || !D) return; busy = true;
    veil('<img class="logo" src="brand/emblem.png" alt=""><div class="xt">Готую PDF…</div><div class="xm">Кілька секунд</div>');
    let restore = null;
    try {
      LOGO = LOGO || await img('brand/emblem.png');
      const libP = window.jspdf ? Promise.resolve() : script('https://unpkg.com/jspdf@2.5.1/dist/jspdf.umd.min.js');
      const W = 1754, H = 1240, M = 64, MW = 1100, MH = 900;
      restore = await stage(MW, MH, 2); draw(1); await idle();
      const c = document.createElement('canvas'); c.width = W; c.height = H; const g = c.getContext('2d');
      const bg = g.createLinearGradient(0, 0, 0, H); bg.addColorStop(0, '#080B12'); bg.addColorStop(1, '#0B1220'); g.fillStyle = bg; g.fillRect(0, 0, W, H);
      // шапка
      brand(g, M, 34, 104);
      g.textAlign = 'right'; g.fillStyle = '#F2F5FA'; g.font = '800 40px ' + FONT; g.fillText('МАПА ДОБИ', W - M, 76);
      g.font = '700 22px ' + FONT; g.fillStyle = GOLD; g.fillText(OBLN().toUpperCase(), W - M, 110);
      g.font = '600 20px ' + FONT; g.fillStyle = MUTE; g.fillText(dateLine() + (D.final ? '' : ' · доба ще триває'), W - M, 138);
      grad(g, M, 162, W - 2 * M, 3);
      // мапа
      const my = 190;
      g.save(); rr(g, M, my, MW, MH, 22); g.clip(); cover(g, map.getCanvas(), M, my, MW, MH);
      g.fillStyle = 'rgba(0,0,0,.55)'; g.fillRect(M, my + MH - 30, MW, 30);
      g.font = '500 14px ' + FONT; g.fillStyle = 'rgba(255,255,255,.7)'; g.textAlign = 'left';
      g.fillText('© Esri, Maxar · © OpenStreetMap · OpenFreeMap · зона контролю: відкриті джерела', M + 14, my + MH - 10);
      g.restore(); g.strokeStyle = 'rgba(255,255,255,.12)'; g.lineWidth = 1.5; rr(g, M, my, MW, MH, 22); g.stroke();
      // права колонка
      const rx = M + MW + 36, rw = W - M - rx; let y = my;
      const cards = [['Маршрутів', D.tracks.filter(t => t.inO).length, '#F2F5FA'], ['Місць з вибухами', VB.length, '#FF8A5B'],
        ['Місць пусків', VS.length, '#FF3D55'], [OBL ? 'Збито по Україні' : 'Збито, ПС ЗСУ', D.official ? D.official.shot : '—', BLUE]];
      const cw = (rw - 16) / 2, ch = 112;
      cards.forEach(([l, v, col], i) => {
        const x = rx + (i % 2) * (cw + 16), yy = y + Math.floor(i / 2) * (ch + 16);
        g.fillStyle = 'rgba(255,255,255,.05)'; rr(g, x, yy, cw, ch, 16); g.fill(); g.strokeStyle = 'rgba(255,255,255,.08)'; g.stroke();
        g.textAlign = 'left'; g.fillStyle = col; g.font = '800 46px ' + FONT; g.fillText(String(v), x + 18, yy + 60);
        g.fillStyle = MUTE; g.font = '600 16px ' + FONT; g.fillText(fit(g, l, cw - 30), x + 18, yy + 92);
      });
      y += 2 * (ch + 16) + 18;
      g.fillStyle = '#F2F5FA'; g.font = '800 17px ' + FONT; g.fillText('ЗА ТИПАМИ', rx, y); y += 14;
      for (const [k, n] of counts().slice(0, 9)) {
        y += 32; g.fillStyle = T[k][1]; if (DASH.has(k)) for (let d = 0; d < 34; d += 12) { rr(g, rx + d, y - 11, 7, 6, 2); g.fill(); } else { rr(g, rx, y - 11 + (MAIN.has(k) ? 0 : 2), 34, MAIN.has(k) ? 6 : 3, 2); g.fill(); }
        g.fillStyle = '#DDE3EE'; g.font = '600 18px ' + FONT; g.textAlign = 'left'; g.fillText(T[k][0], rx + 48, y - 2);
        g.textAlign = 'right'; g.font = '700 18px ' + FONT; g.fillText(String(n), rx + rw, y - 2);
      }
      y += 44; g.textAlign = 'left'; g.fillStyle = '#F2F5FA'; g.font = '800 17px ' + FONT; g.fillText('НАЙБІЛЬШЕ ВИБУХІВ', rx, y); y += 6;
      const top = VB.slice().sort((a, b) => b.c - a.c).slice(0, Math.max(3, Math.floor((my + MH - y - 10) / 30)));
      if (!top.length) { y += 30; g.fillStyle = MUTE; g.font = '500 17px ' + FONT; g.fillText('Повідомлень про вибухи немає', rx, y); }
      for (const b of top) { y += 30; if (y > my + MH) break; g.fillStyle = '#C9D2E3'; g.font = '600 17px ' + FONT; g.textAlign = 'left'; g.fillText(fit(g, b.n, rw - 60), rx, y);
        g.textAlign = 'right'; g.fillStyle = '#FF8A5B'; g.font = '700 17px ' + FONT; g.fillText('×' + b.c, rx + rw, y); }
      // підвал
      const fy = H - 74; grad(g, M, fy - 22, W - 2 * M, 1);
      g.textAlign = 'left'; g.fillStyle = MUTE; g.font = '500 15px ' + FONT;
      g.fillText('Маршрути відтворено з повідомлень моніторингових каналів і приблизні. Кількість цілей дивіться в підсумку Повітряних сил.', M, fy + 4);
      g.fillText('NAVRYX SKY не є офіційною системою оповіщення.', M, fy + 28);
      g.textAlign = 'right'; g.fillStyle = '#F2F5FA'; g.font = '700 17px ' + FONT; g.fillText(SITE, W - M, fy + 4);
      g.fillStyle = MUTE; g.font = '500 14px ' + FONT; g.fillText('Створено ' + nowStr(), W - M, fy + 28);
      await restore(); restore = null;
      await libP;
      const { jsPDF } = window.jspdf;
      const doc = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4', compress: true });
      doc.setProperties({ title: 'NAVRYX SKY · Мапа доби · ' + OBLN() + ' · ' + DAY, author: 'NAVRYX SKY', creator: SITE });
      doc.addImage(c.toDataURL('image/jpeg', 0.9), 'JPEG', 0, 0, 297, 210, undefined, 'FAST');
      doc.link(297 - 70, 210 - 16, 64, 8, { url: 'https://' + SITE + '/daily.html?d=' + DAY + (OBL ? '&o=' + encodeURIComponent(OBL) : '') });
      ready(doc.output('blob'), fname('pdf'), 'pdf', '<img class="pv" src="' + c.toDataURL('image/jpeg', 0.7) + '" alt="">');
    } catch (e) {
      console.error(e); veil('<div class="xt">Не вдалося створити PDF</div><div class="xm">Перевірте з\'єднання й спробуйте ще раз</div><div class="acts"><button id="xcl">Закрити</button></div>');
      document.getElementById('xcl').onclick = unveil;
    } finally { if (restore) await restore(); busy = false; }
  }

  // ---------- Відео ----------
  function pickMime() {
    if (!window.MediaRecorder) return null;
    for (const m of ['video/mp4;codecs=avc1.42E01E', 'video/mp4;codecs=avc1', 'video/mp4', 'video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm'])
      if (MediaRecorder.isTypeSupported(m)) return m;
    return null;
  }
  async function video() {
    if (busy || !D) return;
    const mime = pickMime(), c0 = document.createElement('canvas');
    if (!mime || !c0.captureStream) { veil('<div class="xt">Цей браузер не вміє записувати відео</div><div class="xm">Спробуйте Safari або Chrome останньої версії</div><div class="acts"><button id="xcl">Закрити</button></div>'); document.getElementById('xcl').onclick = unveil; return; }
    busy = true;
    const v = veil('<img class="logo" src="brand/emblem.png" alt=""><div class="xt">Записую відео…</div><div class="xm">Близько 15 секунд, не закривайте сторінку</div><div class="bar"><i></i></div>');
    const bar = v.querySelector('.bar i');
    let restore = null;
    try {
      LOGO = LOGO || await img('brand/emblem.png');
      const W = 1080, H = 1350, MH = 1050, MY = 170;
      restore = await stage(W, MH, 1); draw(0); await idle();
      const c = c0; c.width = W; c.height = H; const g = c.getContext('2d');
      const mc = map.getCanvas();
      const INTRO = 1.6, PLAY = 10, HOLD = 1.6, OUTRO = 2.2, TOT = INTRO + PLAY + HOLD + OUTRO;
      const cs = c.captureStream(30), rec = new MediaRecorder(cs, { mimeType: mime, videoBitsPerSecond: 6e6 }), parts = [];
      rec.ondataavailable = e => { if (e.data && e.data.size) parts.push(e.data); };
      const stopped = new Promise(r => rec.onstop = r);
      const cnt = counts();
      const frame = (t) => {
        const f = Math.max(0, Math.min(1, (t - INTRO) / PLAY));
        g.fillStyle = '#070A10'; g.fillRect(0, 0, W, H);
        g.drawImage(mc, 0, 0, mc.width, mc.height, 0, MY, W, MH);
        // верх
        const tg = g.createLinearGradient(0, MY, 0, MY + 120); tg.addColorStop(0, '#070A10'); tg.addColorStop(1, 'rgba(7,10,16,0)'); g.fillStyle = tg; g.fillRect(0, MY, W, 120);
        brand(g, 48, 34, 96);
        g.textAlign = 'right'; g.fillStyle = '#F2F5FA'; g.font = '800 34px ' + FONT; g.fillText('МАПА ДОБИ', W - 48, 76);
        g.fillStyle = GOLD; g.font = '700 22px ' + FONT; g.fillText(OBLN(), W - 48, 108);
        g.fillStyle = MUTE; g.font = '600 18px ' + FONT; g.fillText(fd(D.t0) + ' – ' + fd(D.t1), W - 48, 134);
        grad(g, 48, 154, W - 96, 2);
        // низ: годинник і лічильники
        const by = MY + MH, bg2 = g.createLinearGradient(0, by - 140, 0, by); bg2.addColorStop(0, 'rgba(7,10,16,0)'); bg2.addColorStop(1, '#070A10'); g.fillStyle = bg2; g.fillRect(0, by - 140, W, 140);
        const T1 = D.t0 + (Math.min(D.t1, D.built) - D.t0) * f;
        g.textAlign = 'left'; g.fillStyle = '#F2F5FA'; g.font = '800 64px ' + FONT; g.fillText(hm(T1), 48, by + 20);
        g.fillStyle = MUTE; g.font = '600 18px ' + FONT; g.fillText('за київським часом', 48, by + 48);
        grad(g, 48, by + 66, (W - 96) * f, 4); g.fillStyle = 'rgba(255,255,255,.08)'; g.fillRect(48 + (W - 96) * f, by + 66, (W - 96) * (1 - f), 4);
        let x = 48, yy = by + 108; g.font = '600 19px ' + FONT;
        for (const [k] of cnt.slice(0, 6)) { const w = g.measureText(T[k][0]).width; if (x + w + 40 > W - 48) { x = 48; yy += 30; if (yy > H - 10) break; }
          g.fillStyle = T[k][1]; if (DASH.has(k)) for (let d = 0; d < 22; d += 9) { rr(g, x + d, yy - 9, 5, 5, 2); g.fill(); } else { rr(g, x, yy - 9, 22, 5, 2.5); g.fill(); } g.fillStyle = '#DDE3EE'; g.textAlign = 'left'; g.fillText(T[k][0], x + 30, yy); x += w + 58; }
        g.textAlign = 'right'; g.fillStyle = 'rgba(255,255,255,.75)'; g.font = '700 20px ' + FONT; g.fillText(SITE, W - 48, by + 20);
        if (D.official) { g.fillStyle = BLUE; g.font = '800 34px ' + FONT; g.fillText(String(D.official.shot), W - 48, by + 62 - 4);
          g.fillStyle = MUTE; g.font = '600 15px ' + FONT; g.fillText('збито / подавлено (ПС ЗСУ)', W - 48 - 0, by + 62 + 16); }
        // інтро й фінальна картка поверх
        const card = (a, title, sub2) => { g.globalAlpha = a; g.fillStyle = '#070A10'; g.fillRect(0, 0, W, H); if (LOGO) g.drawImage(LOGO, W / 2 - 150, H / 2 - 290, 300, 300);
          g.textAlign = 'center'; g.font = '800 64px ' + FONT; const w1 = g.measureText('NAVRYX ').width, w2 = g.measureText('SKY').width, x0 = W / 2 - (w1 + w2) / 2;
          g.textAlign = 'left'; g.fillStyle = '#F2F5FA'; g.fillText('NAVRYX', x0, H / 2 + 90); g.fillStyle = BLUE; g.fillText('SKY', x0 + w1, H / 2 + 90);
          g.textAlign = 'center'; g.fillStyle = '#C9D2E3'; g.font = '600 30px ' + FONT; g.fillText(title, W / 2, H / 2 + 150);
          g.fillStyle = MUTE; g.font = '600 24px ' + FONT; g.fillText(sub2, W / 2, H / 2 + 196); g.globalAlpha = 1; };
        if (t < INTRO) card(t < INTRO - 0.5 ? 1 : (INTRO - t) / 0.5, 'Мапа доби · ' + OBLN(), dateLine());
        if (t > INTRO + PLAY + HOLD) card(Math.min(1, (t - INTRO - PLAY - HOLD) / 0.5), 'Розумій, що відбувається в небі', SITE);
        return f;
      };
      frame(0); rec.start(250);
      const t0 = performance.now(); let lastF = -1;
      await new Promise(done => {
        const step = () => {
          const t = (performance.now() - t0) / 1000; bar.style.width = Math.min(100, t / TOT * 100) + '%';
          const f = frame(t);
          if (f !== lastF) { draw(f >= 1 ? 1 : f); lastF = f; }
          if (t >= TOT) return done();
          requestAnimationFrame(step);
        };
        requestAnimationFrame(step);
      });
      rec.stop(); await stopped;
      await restore(); restore = null;
      const blob = new Blob(parts, { type: mime.split(';')[0] });
      ready(blob, fname(mime.startsWith('video/mp4') ? 'mp4' : 'webm'), 'video', '<video class="pv" playsinline controls muted autoplay loop></video>');
    } catch (e) {
      console.error(e); veil('<div class="xt">Не вдалося записати відео</div><div class="acts"><button id="xcl">Закрити</button></div>'); document.getElementById('xcl').onclick = unveil;
    } finally { if (restore) await restore(); busy = false; }
  }

  document.getElementById('pdf').onclick = pdf;
  document.getElementById('vid').onclick = video;
  window.__DX = { pdf, video };
})();
