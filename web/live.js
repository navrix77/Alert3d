/* «SKY: Живий ефір» (03.11): мапа сама розповідає, що змінилося, поки вас не було, і відповідає на питання діями на мапі.
   Сервер рахує різницю з перевірених даних (/api/since, /api/live), модель лише обирає дозволені дії; без моделі —
   детермінований сценарій. Голос: українська озвучка сервера (/api/tts). Відліку до удару немає. */
(function () {
  'use strict';
  const $ = s => document.querySelector(s);
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const hm = t => new Date(t * 1000).toLocaleTimeString('uk-UA', { hour: '2-digit', minute: '2-digit' });
  const LS = { get: k => { try { return localStorage.getItem(k); } catch (e) { return null; } }, set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) {} } };
  const NX = () => window.NX;
  let seen = +(LS.get('live_seen') || 0), playing = false, stop = false, audioOn = LS.get('live_audio') === '1', shelter = false, shelterT = null, lastSpoken = 0;
  let curDiff = null, abortAudio = null;

  // ---------- що людина вже бачила: оновлюємо, доки застосунок на екрані (і не йде ефір)
  const markSeen = () => { if (!document.hidden && !playing && NX()) { seen = NX().now(); LS.set('live_seen', String(Math.round(seen))); } };
  setInterval(markSeen, 20000);

  // ---------- інтерфейс
  const css = `
  #live-btn{position:fixed;right:12px;bottom:calc(env(safe-area-inset-bottom,0px) + 150px);z-index:40;border-radius:999px;padding:9px 13px;
    background:rgba(18,20,30,.86);border:1px solid rgba(255,255,255,.22);color:#fff;font:700 13px system-ui,sans-serif;backdrop-filter:blur(10px)}
  #live-btn i{display:inline-block;width:8px;height:8px;border-radius:50%;background:#FF4D5E;margin-right:6px;vertical-align:1px}
  #live{position:fixed;left:10px;right:10px;bottom:calc(env(safe-area-inset-bottom,0px) + 92px);z-index:60;max-width:560px;margin:0 auto;
    background:rgba(12,14,22,.94);border:1px solid rgba(255,255,255,.18);border-radius:18px;padding:12px 12px 10px;color:#fff;
    font:14px/1.45 system-ui,sans-serif;box-shadow:0 12px 40px rgba(0,0,0,.5);backdrop-filter:blur(12px)}
  #live .lv-h{display:flex;align-items:center;gap:6px;font-weight:800;font-size:12px;letter-spacing:.02em;white-space:nowrap}
  #live .lv-h button{padding:4px 9px;font-size:12px}
  #live .lv-h i{width:8px;height:8px;border-radius:50%;background:#FF4D5E}
  #live .lv-h .sp{flex:1}
  #live button{background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.2);color:#fff;border-radius:999px;padding:5px 10px;font:600 12.5px system-ui,sans-serif}
  #live button.on{background:rgba(120,160,255,.28);border-color:rgba(150,180,255,.6)}
  #live .lv-say{margin:8px 0 6px;font-size:15.5px;font-weight:600;min-height:44px}
  #live .lv-x{max-height:150px;overflow:auto;font-size:12.5px;opacity:.92}
  #live .lv-x li{margin:3px 0;list-style:none}#live .lv-x ol{padding:0;margin:4px 0}
  #live .lv-x small{opacity:.65}
  #live .lv-q{display:flex;gap:6px;margin-top:8px}
  #live .lv-q input{flex:1;min-width:0;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.2);border-radius:999px;color:#fff;padding:7px 12px;font:14px system-ui,sans-serif}
  #live .lv-note{font-size:11px;opacity:.55;margin-top:6px}
  #live-lasso{position:fixed;inset:0;z-index:55;touch-action:none;cursor:crosshair}
  #live-tip{position:fixed;top:calc(env(safe-area-inset-top,0px) + 70px);left:50%;transform:translateX(-50%);z-index:61;background:rgba(12,14,22,.92);
    color:#fff;border:1px solid rgba(255,255,255,.2);border-radius:14px;padding:10px 12px;font:14px system-ui,sans-serif;display:flex;gap:8px;align-items:center;max-width:92vw}
  #live-tip button{background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.25);color:#fff;border-radius:999px;padding:5px 10px;font:600 13px system-ui,sans-serif}`;
  const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);
  const btn = document.createElement('button'); btn.id = 'live-btn'; btn.innerHTML = '<i></i>Ефір'; btn.title = 'Живий ефір: що змінилося і питання до мапи';
  document.body.appendChild(btn);
  const box = document.createElement('div'); box.id = 'live'; box.hidden = true;
  box.innerHTML = `<div class="lv-h"><i></i><span>ЖИВИЙ ЕФІР</span><span class="sp"></span>
      <button id="lv-audio" title="Озвучувати">🔊</button><button id="lv-shelter" title="Короткі голосові оновлення, поки ви в укритті">Я в укритті</button>
      <button id="lv-pause">❚❚</button><button id="lv-close">✕</button></div>
    <div class="lv-say" id="lv-say"></div><div class="lv-x" id="lv-x"></div>
    <div class="lv-q"><input id="lv-in" placeholder="Спитайте: чому стало 6? що нового? звідки відомо?" enterkeyhint="send">
      <button id="lv-mic" title="Сказати голосом">🎤</button><button id="lv-lasso" title="Обвести ділянку на мапі">✎</button><button id="lv-go">➤</button></div>
    <div class="lv-note" id="lv-note">Лише перевірені дані SKY; без відліку до удару</div>`;
  document.body.appendChild(box);
  const say = $('#lv-say'), xtra = $('#lv-x');
  $('#lv-audio').classList.toggle('on', audioOn);

  // ---------- голос
  async function speak(text) {
    if (!audioOn || !text) return;
    try {
      const a = new Audio('/api/tts?text=' + encodeURIComponent(text.slice(0, 300)) + '&voice=' + (LS.get('voice') || 'lada'));
      await new Promise(res => { abortAudio = () => { try { a.pause(); } catch (e) {} res(); }; a.onended = res; a.onerror = res; a.play().catch(res); setTimeout(res, 20000); });
    } catch (e) {}
  }
  const wait = ms => new Promise(r => setTimeout(r, ms));

  // ---------- дії мапи
  function bboxOf(pts) { let b = [180, 90, -180, -90]; for (const p of pts) if (p) b = [Math.min(b[0], p[0]), Math.min(b[1], p[1]), Math.max(b[2], p[0]), Math.max(b[3], p[1])]; return b[0] <= b[2] ? b : null; }
  function fit(pts, maxZoom) { const m = NX().map(), b = bboxOf(pts); if (!m || !b) return;
    if (b[2] - b[0] < 0.02 && b[3] - b[1] < 0.02) { m.flyTo({ center: [b[0], b[1]], zoom: Math.min(maxZoom || 10, 10), duration: 900 }); return; }
    m.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: { top: 120, bottom: 330, left: 40, right: 40 }, maxZoom: maxZoom || 10, duration: 900 }); }
  const item = id => curDiff && curDiff.items.find(i => i.id === id);
  function hl(ids, dim) { window.FXLIVE = { ids: new Set(ids || []), dim: !!dim, t0: performance.now() }; const m = NX().map(); m && m.triggerRepaint(); }
  function mentions(it) {
    if (!it) return '';
    const ms = it.mentions || [];
    return '<b>' + esc(it.name) + (it.count > 1 ? ' ×' + it.count : '') + '</b>' + (it.count_was && it.count_was !== it.count ? ' · було ' + it.count_was + ' → стало ' + it.count : '') +
      (it.ai ? ' · ✦ розпізнано ШІ' : '') + (ms.length ? '<ol>' + ms.map(e => '<li><small>' + hm(e.t) + '</small> <b>' + esc(NX().src(e.src)) + '</b>' +
        (e.copy ? ' <small>(копія)</small>' : '') + ': ' + esc(e.text) + (e.link ? ' <a href="' + esc(e.link) + '" target=_blank rel=noopener>↗</a>' : '') + '</li>').join('') + '</ol>'
        : '<br><small>Нових згадок з того часу немає</small>') +
      (it.count_was && it.count_was !== it.count ? '<br><small>Кількість називають канали; якщо версії різні, SKY бере найбільшу названу для однієї групи</small>' : '');
  }
  function act(s) {
    const ids = s.ids || [];
    xtra.innerHTML = '';
    switch (s.action) {
      case 'overview': { const pts = (curDiff.items || []).map(i => [i.lon, i.lat]); const h = NX().home(); if (h) pts.push(h); hl([], false); fit(pts, 9); break; }
      case 'focus': hl(ids, true); fit(ids.map(i => NX().pos(i) || (item(i) && [item(i).lon, item(i).lat])), 10); break;
      case 'highlight': hl(ids, false); break;
      case 'dim': hl(window.FXLIVE ? [...window.FXLIVE.ids] : [], s.value !== false); break;
      case 'only_new': { const n = curDiff.items.filter(i => i.status === 'new' || i.status === 'changed').map(i => i.id); hl(n, true);
        fit(n.map(i => NX().pos(i)), 10); xtra.innerHTML = n.length ? n.map(i => mentions(item(i))).join('<hr style="opacity:.15">') : 'Нового з того часу немає'; break; }
      case 'breakdown': case 'sources': hl(ids, true); fit(ids.map(i => NX().pos(i)), 10); xtra.innerHTML = ids.map(i => mentions(item(i))).join('<hr style="opacity:.15">'); break;
      case 'region': if (s.bbox) { fit([[s.bbox[0], s.bbox[1]], [s.bbox[2], s.bbox[3]]], 11); } break;
      case 'replay': hl(curDiff.items.filter(i => i.status !== 'same').map(i => i.id), true); break;
    }
  }
  async function run(steps) {
    playing = true; stop = false; box.hidden = false; $('#lv-pause').textContent = '❚❚';
    for (const s of steps) {
      if (stop) break;
      say.textContent = s.say || ''; act(s);
      const t0 = Date.now(); await speak(s.say);
      const rest = Math.max(0, Math.min(6500, 1800 + (s.say || '').length * 45) - (Date.now() - t0));
      for (let k = 0; k < rest && !stop; k += 200) await wait(200);
      while (paused && !stop) await wait(200);
    }
    playing = false;
  }
  let paused = false;

  // ---------- запити
  function where() { const h = NX().home(); return { obl: NX().homeObl() || '', lat: h ? h[1] : null, lon: h ? h[0] : null }; }
  async function live(q, bbox, t) {
    const w = where();
    say.textContent = q ? 'Дивлюся…' : 'Збираю, що змінилося…'; xtra.innerHTML = ''; box.hidden = false;
    try {
      const r = await (await fetch('/api/live', { method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ t: t || seen || (NX().now() - 1800), q: q || '', bbox: bbox || null, ...w }) })).json();
      curDiff = r.diff; $('#lv-note').textContent = (r.by && r.by !== 'rules' ? 'Сценарій ШІ (' + r.by.split(':')[0] + ') з перевірених даних SKY' : 'Сценарій з перевірених даних SKY') + '; без відліку до удару';
      await run(r.steps || []);
      return r;
    } catch (e) { say.textContent = 'Не вдалося отримати дані. Перевірте з’єднання.'; }
  }
  function start(manual) { stop = true; if (abortAudio) abortAudio(); setTimeout(() => live(null, null, manual ? seen : seen), 50); }
  btn.onclick = () => { $('#live-tip') && $('#live-tip').remove(); start(true); };
  $('#lv-close').onclick = () => { stop = true; paused = false; if (abortAudio) abortAudio(); box.hidden = true; hl([], false); window.FXLIVE = null; markSeen(); };
  $('#lv-pause').onclick = () => { paused = !paused; $('#lv-pause').textContent = paused ? '▶' : '❚❚'; if (paused && abortAudio) abortAudio(); };
  $('#lv-audio').onclick = () => { audioOn = !audioOn; LS.set('live_audio', audioOn ? '1' : '0'); $('#lv-audio').classList.toggle('on', audioOn); if (!audioOn && abortAudio) abortAudio(); };
  const ask = q => { if (!q) return; stop = true; paused = false; if (abortAudio) abortAudio(); $('#lv-in').value = ''; setTimeout(() => live(q, lassoBox), 60); lassoBox = null; };
  $('#lv-go').onclick = () => ask($('#lv-in').value.trim());
  $('#lv-in').onkeydown = e => { if (e.key === 'Enter') ask($('#lv-in').value.trim()); };

  // ---------- голосове питання (де браузер уміє розпізнавати мову)
  // iPhone/iPad (і PWA на них): вбудоване розпізнавання браузера ненадійне — записуємо голос і розпізнаємо на сервері
  // (Whisper через OpenAI/Groq, українська). На Android Chrome — вбудоване розпізнавання браузера, з тим самим запасним шляхом.
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const IOS = /iP(hone|ad|od)/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const canRec = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
  if (!SR && !canRec) $('#lv-mic').hidden = true;
  let rec = null;
  async function recordAndAsk() {
    const mic = $('#lv-mic');
    if (rec) { try { rec.stop(); } catch (e) {} return; }  // друге торкання — стоп
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } }); }
    catch (e) { say.textContent = 'Немає доступу до мікрофона. Дозвольте його в Налаштуваннях → Safari (або для застосунку) → Мікрофон.'; return; }
    const mt = ['audio/mp4', 'audio/aac', 'audio/webm;codecs=opus', 'audio/webm'].find(t => MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || '';
    const chunks = []; rec = new MediaRecorder(stream, mt ? { mimeType: mt } : undefined);
    rec.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data); };
    // автостоп: 1,3 с тиші після мовлення або 10 с загалом
    let ctx, stopT = setTimeout(() => rec && rec.state === 'recording' && rec.stop(), 10000);
    try { ctx = new (window.AudioContext || window.webkitAudioContext)(); const an = ctx.createAnalyser(); an.fftSize = 1024; ctx.createMediaStreamSource(stream).connect(an);
      const buf = new Uint8Array(an.fftSize); let spoke = false, quietSince = 0;
      const tick = () => { if (!rec || rec.state !== 'recording') return; an.getByteTimeDomainData(buf); let m = 0; for (const v of buf) m = Math.max(m, Math.abs(v - 128));
        const now = performance.now(); if (m > 18) { spoke = true; quietSince = 0; } else if (spoke) { quietSince = quietSince || now; if (now - quietSince > 1300) { rec.stop(); return; } }
        requestAnimationFrame(tick); }; requestAnimationFrame(tick); } catch (e) {}
    rec.onstop = async () => {
      clearTimeout(stopT); stream.getTracks().forEach(t => t.stop()); try { ctx && ctx.close(); } catch (e) {}
      mic.classList.remove('on'); mic.textContent = '🎤'; const type = rec.mimeType || mt || 'audio/mp4'; rec = null; paused = false;
      const blob = new Blob(chunks, { type }); if (blob.size < 2000) { say.textContent = 'Не почув. Торкніться 🎤 і скажіть питання.'; return; }
      say.textContent = 'Розпізнаю…';
      try { const r = await (await fetch('/api/stt', { method: 'POST', headers: { 'content-type': type }, body: blob })).json();
        if (r.text) { $('#lv-in').value = r.text; ask(r.text); } else say.textContent = 'Не вдалося розпізнати. Спробуйте ще раз або напишіть питання (на клавіатурі iPhone є 🎙 диктування).';
      } catch (e) { say.textContent = 'Немає зв’язку з сервером для розпізнавання.'; }
    };
    paused = true; if (abortAudio) abortAudio();
    mic.classList.add('on'); mic.textContent = '■'; say.textContent = 'Говоріть… (торкніться ■, щоб закінчити)';
    rec.start(250);
  }
  function browserSR() {
    const r = new SR(); r.lang = 'uk-UA'; r.interimResults = false; r.maxAlternatives = 1; let got = false;
    $('#lv-mic').classList.add('on'); paused = true; if (abortAudio) abortAudio();
    r.onresult = e => { got = true; const q = e.results[0][0].transcript; $('#lv-in').value = q; ask(q); };
    r.onend = () => { $('#lv-mic').classList.remove('on'); paused = false; };
    r.onerror = e => { $('#lv-mic').classList.remove('on'); paused = false; if (!got && canRec && /not-allowed|service|network|audio/.test(e.error || '')) recordAndAsk(); };
    try { r.start(); } catch (e) { if (canRec) recordAndAsk(); }
  }
  $('#lv-mic').onclick = () => { if (IOS || !SR) { if (canRec) recordAndAsk(); } else browserSR(); };

  // ---------- обвести ділянку пальцем
  let lassoBox = null;
  $('#lv-lasso').onclick = () => {
    const m = NX().map(); if (!m) return;
    const cv = document.createElement('canvas'); cv.id = 'live-lasso'; cv.width = innerWidth * devicePixelRatio; cv.height = innerHeight * devicePixelRatio;
    cv.style.width = innerWidth + 'px'; cv.style.height = innerHeight + 'px'; document.body.appendChild(cv);
    const g = cv.getContext('2d'); g.scale(devicePixelRatio, devicePixelRatio); g.strokeStyle = '#fff'; g.lineWidth = 3; g.setLineDash([6, 6]);
    say.textContent = 'Обведіть пальцем ділянку на мапі'; const pts = [];
    cv.onpointerdown = e => { pts.length = 0; pts.push([e.clientX, e.clientY]); cv.setPointerCapture(e.pointerId); };
    cv.onpointermove = e => { if (!pts.length) return; pts.push([e.clientX, e.clientY]); g.clearRect(0, 0, innerWidth, innerHeight); g.beginPath(); pts.forEach((p, i) => i ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1])); g.stroke(); };
    cv.onpointerup = () => { cv.remove(); if (pts.length < 5) return;
      const ll = pts.map(p => { const q = m.unproject(p); return [q.lng, q.lat]; }); lassoBox = bboxOf(ll);
      const q = $('#lv-in').value.trim() || 'Поясни, що на цій ділянці'; ask(q); };
  };

  // ---------- «Я в укритті»: короткі голосові оновлення лише про зміни для свого району
  $('#lv-shelter').onclick = async () => {
    shelter = !shelter; $('#lv-shelter').classList.toggle('on', shelter);
    if (!shelter) { clearInterval(shelterT); shelterT = null; return; }
    audioOn = true; LS.set('live_audio', '1'); $('#lv-audio').classList.add('on');
    lastSpoken = NX().now();
    try { if ('wakeLock' in navigator) await navigator.wakeLock.request('screen'); } catch (e) {}
    say.textContent = 'Режим укриття: озвучуватиму лише зміни для вашого району. Екран можна притушити, застосунок тримайте відкритим.';
    await speak('Режим укриття. Озвучуватиму лише зміни для вашого району.');
    shelterT = setInterval(async () => {
      if (playing) return; const w = where();
      try {
        const d = await (await fetch('/api/since?t=' + Math.round(lastSpoken) + '&obl=' + encodeURIComponent(w.obl) + (w.lat != null ? '&lat=' + w.lat + '&lon=' + w.lon : ''))).json();
        const c = d.counts || {};
        if (c.new || c.changed || (d.bal || []).length || (d.alert && d.alert.now !== d.alert.was)) { lastSpoken = d.now; await live(null, null, d.since); }
      } catch (e) {}
    }, 60000);
  };

  // ---------- повернення після відсутності: запропонувати ефір
  function offer() {
    if (!NX() || playing || !box.hidden) return;
    const gap = NX().now() - seen;
    if (!seen || gap < 300) return;
    const tip = document.createElement('div'); tip.id = 'live-tip';
    tip.innerHTML = '<span>Вас не було ' + Math.round(gap / 60) + ' хв. Показати, що змінилося для вашого району?</span><button id="lt-y">Показати</button><button id="lt-n">✕</button>';
    $('#live-tip') && $('#live-tip').remove(); document.body.appendChild(tip);
    $('#lt-y').onclick = () => { tip.remove(); start(true); };
    $('#lt-n').onclick = () => { tip.remove(); markSeen(); };
    setTimeout(() => { if (tip.isConnected) { tip.remove(); } }, 20000);
  }
  document.addEventListener('visibilitychange', () => { if (!document.hidden) setTimeout(offer, 1500); else markSeen(); });
  setTimeout(offer, 4000);
})();
