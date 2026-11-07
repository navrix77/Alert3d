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
  #live-btn{position:fixed;left:10px;top:calc(max(8px,env(safe-area-inset-top,0px)) + 108px);z-index:4;border-radius:16px;padding:6px 12px 6px 11px;
    background:rgba(18,20,30,.9);border:1px solid rgba(255,120,130,.55);color:#fff;font:800 14px/1.15 system-ui,sans-serif;backdrop-filter:blur(10px);
    display:flex;align-items:center;gap:8px;text-align:left;box-shadow:0 4px 18px rgba(0,0,0,.45)}
  #live-btn i{display:inline-block;width:9px;height:9px;border-radius:50%;background:#FF4D5E;flex:none;animation:lvp 1.6s infinite}
  #live-btn small{display:block;font:600 11px system-ui,sans-serif;opacity:.7}
  #live-btn.new{border-color:#FFB020;box-shadow:0 0 0 2px rgba(255,176,32,.35),0 4px 18px rgba(0,0,0,.45)}
  @keyframes lvp{0%,100%{opacity:1}50%{opacity:.35}}
  #radio-btn{position:fixed;left:10px;top:calc(max(8px,env(safe-area-inset-top,0px)) + 60px);z-index:4;width:42px;height:42px;border-radius:50%;padding:0;
    background:rgba(18,20,30,.9);border:1px solid rgba(255,255,255,.25);color:#fff;font-size:20px;line-height:40px;text-align:center;backdrop-filter:blur(10px);box-shadow:0 4px 18px rgba(0,0,0,.45)}
  #radio-btn.on{background:rgba(160,30,45,.95);border-color:rgba(255,140,150,.9);animation:rdp 1.6s infinite}
  @keyframes rdp{0%,100%{box-shadow:0 0 0 0 rgba(255,77,94,.55)}50%{box-shadow:0 0 0 7px rgba(255,77,94,0)}}
  #live .lv-ctl{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap}
  #live:not(.full) .lv-ctl,#live:not(.full) .lv-help,#live:not(.full) .lv-chips,#live:not(.full) .lv-q,#live:not(.full) .lv-note{display:none}
  #live:not(.full) .lv-x{max-height:64px}
  #live:not(.full) .lv-say{margin:6px 0 2px;min-height:0;font-size:15px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
  #live:not(.full){padding:10px 12px 8px}
  #live.full #lv-pause2{display:none}
  body.live-on #me{display:none!important}
  #live .lv-help{font-size:12px;opacity:.7;margin-top:2px}
  #live .lv-chips{display:flex;gap:6px;overflow-x:auto;margin-top:8px;padding-bottom:2px;scrollbar-width:none}
  #live .lv-chips button{white-space:nowrap;flex:none;background:rgba(120,160,255,.14);border-color:rgba(150,180,255,.35)}
  #live{position:fixed;left:10px;right:10px;bottom:calc(env(safe-area-inset-bottom,0px) + 92px);z-index:60;max-width:560px;margin:0 auto;
    background:rgba(12,14,22,.94);border:1px solid rgba(255,255,255,.18);border-radius:18px;padding:12px 12px 10px;color:#fff;
    font:14px/1.45 system-ui,sans-serif;box-shadow:0 12px 40px rgba(0,0,0,.5);backdrop-filter:blur(12px)}
  #live .lv-h{display:flex;align-items:center;gap:6px;font-weight:800;font-size:12px;letter-spacing:.02em;white-space:nowrap;flex-wrap:wrap;row-gap:6px}
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
  const btn = document.createElement('button'); btn.id = 'live-btn'; btn.innerHTML = '<i></i><span>Ефір<small>що змінилось</small></span>'; btn.title = 'Живий ефір: мапа розповість, що змінилось, і відповість на питання';
  document.body.appendChild(btn);
  const box = document.createElement('div'); box.id = 'live'; box.hidden = true;
  box.innerHTML = `<div class="lv-h"><i></i><span>ЕФІР</span><span class="sp"></span><button id="lv-pause2" title="Пауза">⏸</button><button id="lv-more" title="Питання й налаштування">⋯</button><button id="lv-close" title="Закрити">✕</button></div>
    <div class="lv-ctl"><button id="lv-audio" title="Озвучувати">🔊 Голос</button><button id="lv-shelter" title="Короткі голосові оновлення, поки ви в укритті">🛡 Я в укритті</button>
      <button id="lv-pause" title="Пауза">⏸ Пауза</button></div>
    <div class="lv-help">Мапа сама покаже, що змінилось біля вас, поки вас не було. Можна спитати текстом або голосом.</div>
    <div class="lv-chips"><button data-q="Що нового біля мене?">Що нового біля мене?</button><button data-q="Що летить на мою область?">Що летить на мою область?</button>
      <button data-q="Що зараз по всій Україні?">Що по Україні?</button><button data-q="Звідки це відомо?">Звідки відомо?</button></div>
    <div class="lv-say" id="lv-say"></div><div class="lv-x" id="lv-x"></div>
    <div class="lv-q"><input id="lv-in" placeholder="Спитайте: чому стало 6? що нового? звідки відомо?" enterkeyhint="send">
      <button id="lv-mic" title="Сказати голосом">🎤</button><button id="lv-lasso" title="Обвести ділянку на мапі">✎</button><button id="lv-go">➤</button></div>
    <div class="lv-note" id="lv-note">Лише перевірені дані SKY; без відліку до удару</div>`;
  document.body.appendChild(box);
  const say = $('#lv-say'), xtra = $('#lv-x');
  $('#lv-audio').classList.toggle('on', audioOn);

  // ---------- голос
  const ttsUrl = (text, voice) => '/api/tts?v=4&text=' + encodeURIComponent(text.slice(0, 600)) + '&voice=' + (voice || 'radio');
  // голос наперед: поки звучить позивний чи попередня фраза, наступна вже генерується й завантажується
  const preVoice = (text, voice) => fetch(ttsUrl(text, voice)).then(r => r.ok ? r.blob() : null).then(b => b && b.size > 500 ? URL.createObjectURL(b) : null).catch(() => null);
  const preUrl = url => fetch(url).then(r => r.ok ? r.blob() : null).then(b => b && b.size > 500 ? URL.createObjectURL(b) : null).catch(() => null);
  // запасний голос цілим текстом: сервер приймає до 600 символів, тож довге ділимо на межах речень, а не посеред слова
  const chunks = t => { const out = []; let cur = ''; for (const sn of String(t).match(/[^.!?…]+[.!?…]*\s*/g) || [t]) {
    if ((cur + sn).length > 450 && cur) { out.push(cur.trim()); cur = ''; } cur += sn; } if (cur.trim()) out.push(cur.trim()); return out; };
  async function speak(text, voice, pre) {
    if (!audioOn || !text) return;
    const ready = pre && await pre;
    if (!ready && text.length > 450) { for (const c of chunks(text)) { if (!audioOn) return; await speak(c, voice); } return; }
    try {
      const url = ready || ttsUrl(text, voice);
      if (window.SKYVOICE) { abortAudio = () => window.SKYVOICE.stop(); await window.SKYVOICE.play(url, Math.max(0.1, Math.min(1, +(LS.get('radio_voice_vol') || 1))), 1.12); return; }
      const a = new Audio(url);try{a.volume=Math.max(0.1,Math.min(1,+(LS.get('radio_voice_vol')||1)));}catch(e){}try{a.preservesPitch=true;a.defaultPlaybackRate=a.playbackRate=1.12;}catch(e){}
      await new Promise(res => { abortAudio = () => { try { a.pause(); } catch (e) {} res(); }; a.onended = res; a.onerror = res; a.play().catch(res); setTimeout(res, 120000); });  // 20 с обрізали довгі фрази
    } catch (e) {}
  }
  const wait = ms => new Promise(r => setTimeout(r, ms));

  // ---------- дії мапи
  function bboxOf(pts) { let b = [180, 90, -180, -90]; for (const p of pts) if (p) b = [Math.min(b[0], p[0]), Math.min(b[1], p[1]), Math.max(b[2], p[0]), Math.max(b[3], p[1])]; return b[0] <= b[2] ? b : null; }
  // 04.11 власник: озвучена ціль — у центрі видимої частини мапи (смуга ефіру її не закриває), з наближенням
  function pad() { const r = box.hidden ? null : box.getBoundingClientRect(); let top = 80, bottom = 60;
    if (r && r.height) { if (r.top < innerHeight / 2) top = Math.max(top, r.bottom + 24); else bottom = Math.max(bottom, innerHeight - r.top + 24); }
    return { top: Math.min(top, innerHeight * 0.5), bottom: Math.min(bottom, innerHeight * 0.5), left: 40, right: 40 }; }
  function fit(pts, maxZoom) { const m = NX().map(), b = bboxOf(pts); if (!m || !b) return; const p = pad();
    if (b[2] - b[0] < 0.03 && b[3] - b[1] < 0.03) { m.flyTo({ center: [b[0], b[1]], zoom: Math.min(maxZoom || 10, 9.5), offset: [0, (p.top - p.bottom) / 2], duration: 1000, essential: true }); return; }
    m.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: p, maxZoom: maxZoom || 10, duration: 1000 }); }
  const posOf = ids => ids.map(i => NX().pos(i) || (item(i) && [item(i).lon, item(i).lat]));
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
      case 'focus': hl(ids, true); fit(posOf(ids), 10); break;
      case 'highlight': hl(ids, false); fit(posOf(ids), 10); break;
      case 'dim': hl(window.FXLIVE ? [...window.FXLIVE.ids] : [], s.value !== false); break;
      case 'only_new': { const n = curDiff.items.filter(i => i.status === 'new' || i.status === 'changed').map(i => i.id); hl(n, true);
        fit(n.map(i => NX().pos(i)), 10); xtra.innerHTML = n.length ? n.map(i => mentions(item(i))).join('<hr style="opacity:.15">') : 'Нового з того часу немає'; break; }
      case 'breakdown': case 'sources': hl(ids, true); fit(ids.map(i => NX().pos(i)), 10); xtra.innerHTML = ids.map(i => mentions(item(i))).join('<hr style="opacity:.15">'); break;
      case 'region': if (s.bbox) { fit([[s.bbox[0], s.bbox[1]], [s.bbox[2], s.bbox[3]]], 11); } break;
      case 'replay': hl(curDiff.items.filter(i => i.status !== 'same').map(i => i.id), true); break;
      default: if (ids.length) { hl(ids, false); fit(posOf(ids), 10); }
    }
  }
  async function run(steps) {
    playing = true; stop = false; box.hidden = false; $('#lv-pause').textContent = '⏸ Пауза';
    // голос усіх кроків замовляється одразу (заготовки склеюються миттєво), тож між репліками немає очікування
    const pre = steps.map(s => s.audio && audioOn ? preUrl(s.audio) : null);
    for (const [k, s] of steps.entries()) {
      if (stop) break;
      say.textContent = s.say || ''; act(s);
      const t0 = Date.now(); await speak(s.say, 'radio', pre[k]);
      const rest = audioOn ? 600 : Math.max(0, Math.min(6500, 1800 + (s.say || '').length * 45) - (Date.now() - t0));  // з голосом — без зайвих пауз
      for (let k = 0; k < rest && !stop; k += 200) await wait(200);
      while (paused && !stop) await wait(200);
    }
    playing = false;
    if (!stop) autoClose();
  }
  // 04.11 власник: немає новин і змін — ефір сам вимикається (як радіо мовчить); є зміни — панель зникає за 30 с,
  // якщо людина не відкрила питання (⋯) і не взаємодіє з нею
  let acT = null;
  function autoClose() {
    clearTimeout(acT);
    const c = curDiff && curDiff.counts, quiet = !c || (!c.new && !c.changed && !c.gone && !(curDiff.bal || []).length);
    // 04.11 власник: «після фрази відключай ефір» — остання репліка прозвучала, ефір закривається (якщо людина не читає подробиці)
    acT = setTimeout(() => { if (!playing && !box.hidden && !box.classList.contains('full') && !shelter && document.activeElement !== $('#lv-in')) $('#lv-close').click(); }, quiet ? 1500 : 2500);
  }
  box.addEventListener('pointerdown', () => clearTimeout(acT));
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
  // одночасно працює щось одне: Ефір вимикає Sky Radio (і навпаки)
  btn.onclick = () => { if (radioOn) rbtn.onclick(); btn.classList.remove('new'); btn.querySelector('small').textContent = 'що змінилось'; start(true); };
  $('#lv-more').onclick = () => { box.classList.toggle('full'); };
  $('#lv-pause2').onclick = () => $('#lv-pause').click();
  try { new MutationObserver(() => { document.body.classList.toggle('live-on', !box.hidden); if (box.hidden) box.classList.remove('full'); })
    .observe(box, { attributes: true, attributeFilter: ['hidden'] }); } catch (e) {}
  $('#lv-close').onclick = () => { if (shelter) $('#lv-shelter').click(); stop = true; paused = false; if (abortAudio) abortAudio(); box.hidden = true; hl([], false); window.FXLIVE = null; markSeen(); };
  $('#lv-pause').onclick = () => { paused = !paused; $('#lv-pause').textContent = paused ? '▶ Далі' : '⏸ Пауза'; $('#lv-pause2').textContent = paused ? '▶' : '⏸'; if (paused && abortAudio) abortAudio(); };
  $('#lv-audio').onclick = () => { audioOn = !audioOn; LS.set('live_audio', audioOn ? '1' : '0'); $('#lv-audio').classList.toggle('on', audioOn); if (!audioOn && abortAudio) abortAudio(); };
  const ask = q => { if (!q) return; box.classList.remove('full'); stop = true; paused = false; if (abortAudio) abortAudio(); $('#lv-in').value = ''; setTimeout(() => live(q, lassoBox), 60); lassoBox = null; };
  $('#lv-go').onclick = () => ask($('#lv-in').value.trim());
  box.querySelectorAll('.lv-chips button').forEach(b => b.onclick = () => ask(b.dataset.q));
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

  // ---------- Sky Radio (04.11, переробка): говорить, коли біля вас щось змінилось; без змін мовчить (раз на 8 хв коротко
  // нагадує обстановку); уся Україна — на початку й раз на 15 хв. Звуки як на радіо: позивний, сигнал новин, тривожний сигнал,
  // тиха фонова підкладка, що стихає під голос. Усе синтезовано тут же (власні звуки, не чужа музика).
  let idleSince = 0, radioLast = 0, radioBusy2 = false, radioSid = '', radioOn = false, radioT = null, radioSeen = 0, radioBusy = false, lastCountry = 0;
  const RA = { ctx: null, bed: null, bedGain: null, master: null };
  function raCtx() {
    if (!RA.ctx) { const C = window.AudioContext || window.webkitAudioContext; RA.ctx = new C(); RA.master = RA.ctx.createGain(); RA.master.gain.value = 0.9; RA.master.connect(RA.ctx.destination); }
    if (RA.ctx.state !== 'running') RA.ctx.resume();
    return RA.ctx;
  }
  function tone(freq, t0, dur, vol, type, dest) {
    const c = raCtx(), o = c.createOscillator(), g = c.createGain();
    o.type = type || 'sine'; o.frequency.setValueAtTime(freq, t0);
    g.gain.setValueAtTime(0.0001, t0); g.gain.exponentialRampToValueAtTime(vol, t0 + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    o.connect(g).connect(dest || RA.master); o.start(t0); o.stop(t0 + dur + 0.05);
  }
  // звукове оформлення за концепцією SKY Radio (04.11): фірмовий мотив із трьох чистих «скляних» нот з теплою основою, моно;
  // звичайне оновлення — один м'який тон; важливе — два виразні тони (інший ритм і тембр, не гучніше); збій — нейтральний звук;
  // завершення зведення — скорочений мотив. Без сирен, вибухів, радарних і військових ефектів
  function glass(freq, t0, dur, vol) {  // скляна нота: синус + тихий обертон, м'яка атака, короткий хвіст
    const c = raCtx(), g = c.createGain(), o1 = c.createOscillator(), o2 = c.createOscillator(), g2 = c.createGain();
    o1.type = 'sine'; o1.frequency.value = freq; o2.type = 'sine'; o2.frequency.value = freq * 2.756; g2.gain.value = 0.12;
    g.gain.setValueAtTime(0.0001, t0); g.gain.exponentialRampToValueAtTime(vol, t0 + 0.035); g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    o1.connect(g); o2.connect(g2).connect(g); g.connect(RA.master); o1.start(t0); o2.start(t0); o1.stop(t0 + dur + 0.05); o2.stop(t0 + dur + 0.05);
  }
  function warm(freq, t0, dur, vol) { const c = raCtx(), o = c.createOscillator(), lp = c.createBiquadFilter(), g = c.createGain();
    o.type = 'triangle'; o.frequency.value = freq; lp.type = 'lowpass'; lp.frequency.value = 700;
    g.gain.setValueAtTime(0.0001, t0); g.gain.exponentialRampToValueAtTime(vol, t0 + 0.12); g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    o.connect(lp).connect(g).connect(RA.master); o.start(t0); o.stop(t0 + dur + 0.05); }
  // 04.11 власник: «звуки жахливі, потрібно щось приємне мелодійне» — короткі мелодійні джингли (живі інструменти: steel-drum
  // і піцикато, ліцензія CC0, Kenney), зведені за гучністю; тональність фа мажор для позивного й новин, мінор для важливого
  const SURL = { ident: 'snd/ident.mp3', news: 'snd/news.mp3', calm: 'snd/calm.mp3', urgent: 'snd/urgent.mp3', outro: 'snd/outro.mp3', outage: 'snd/outage.mp3' }, SB = {};
  function sLoad() { const c = raCtx(); return Promise.all(Object.keys(SURL).map(k => SB[k] ? 0 : fetch(SURL[k]).then(r => r.arrayBuffer())
    .then(ab => new Promise((ok, no) => c.decodeAudioData(ab, ok, no))).then(b => { SB[k] = b; }).catch(() => {}))); }
  function sPlay(k, vol) { const b = SB[k]; if (LS.get('radio_sig') === '0') return wait(0);
    if (k !== 'urgent' && k !== 'outage' && window.SKYRADIO && window.SKYRADIO.state() === 'PLAYING_MUSIC') return wait(0);  // під музикою SKY RADIO додаткові сигнали лише додають паузи (07.11)
    if (!b || (window.SKYVOICE && window.SKYVOICE.alerting)) return wait(0);
    try { const c = raCtx(), src = c.createBufferSource(), g = c.createGain(); g.gain.value = vol; src.buffer = b; src.connect(g).connect(RA.master); src.start(); } catch (e) {}
    return wait(Math.max(0, Math.round(b.duration * 1000) - 120)); }
  const SND = { ident: () => sPlay('ident', 0.6), outro: () => sPlay('outro', 0.45), news: () => sPlay('news', 0.42), calm: () => sPlay('calm', 0.3),
    urgent: () => sPlay('urgent', 0.55), outage: () => sPlay('outage', 0.4) };
  // сповіщення поверх радіо: фон приглушується, голос радіо ставить на паузу sound.js
  addEventListener('sky-alert', e => duck(e.detail.on));
  // «Атмосфера ефіру» (налаштування): тиха синтезаторна підкладка між повідомленнями, без мелодії, пульсацій і наростання;
  // під голосом стихає приблизно на 20+ дБ; для важливого, виправлення й збою вимикається. За замовчуванням — «Лише повідомлення»
  // 05.11: фон був майже нечутним (гучність 4%) і в багатьох лишився «Тиша»: один раз скидаємо на «Атмосфера» з помітною гучністю
  if (LS.get('radio_bed_v') !== '4') { LS.set('radio_bed_v', '4'); LS.set('radio_mode', 'music'); }  // 07.11: синтезована «атмосфера» прибрана, замість неї готова музика + джингл SKY RADIO  // 05.11: гучний варіант звучав жахливо — повернено «Тиша» і тиху гучність
  function bedStart() {}  // синтезований фон прибрано (07.11)
  function bedStop() {}
  function duck(on) { try { window.SKYRADIO && window.SKYRADIO.duck(on); } catch (e) {} }

  // налаштування Sky Radio в розділі «Звук»: тиша чи атмосфера між повідомленнями, гучність атмосфери
  (function () { const seg = document.getElementById('rad-mode'), vol = document.getElementById('rad-atmo'); if (!seg) return;
    const mode = () => LS.get('radio_mode') || 'music';
    const sync = () => seg.querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.v === mode()));
    seg.querySelectorAll('button').forEach(b => b.onclick = () => { LS.set('radio_mode', b.dataset.v); sync(); if (radioOn && window.SKYRADIO) { if (b.dataset.v === 'music') window.SKYRADIO.start(); else window.SKYRADIO.stop(); } });
    const vv = document.getElementById('rad-voice'), sg = document.getElementById('rad-sig');
    if (vv) { vv.value = Math.round((+(LS.get('radio_voice_vol') || 1)) * 10); vv.oninput = () => LS.set('radio_voice_vol', String(vv.value / 10)); }
    if (sg) { sg.checked = LS.get('radio_sig') !== '0'; sg.onchange = () => LS.set('radio_sig', sg.checked ? '1' : '0'); }
    if (vol) { vol.value = Math.round((+(LS.get('radio_atmo_vol') || 0.04)) * 100); vol.oninput = () => { LS.set('radio_atmo_vol', String(vol.value / 100)); duck(false); }; }
    sync();
    // охоплення: «Поруч зі мною» (радіус) / «Моя область» / «Вся Україна»; перемикання — нове зведення в новому режимі
    const sc = document.getElementById('rad-scope'), rr = document.getElementById('rad-radius');
    const syncS = () => { sc && sc.querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.v === (LS.get('radio_scope') || 'near')));
      rr && rr.querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.v === String(LS.get('radio_radius') || 25))); };
    sc && sc.querySelectorAll('button').forEach(b => b.onclick = () => { LS.set('radio_scope', b.dataset.v); syncS(); if (radioOn) { window.SKYVOICE && window.SKYVOICE.stop(); radioIssue(); } });
    rr && rr.querySelectorAll('button').forEach(b => b.onclick = () => { LS.set('radio_radius', b.dataset.v); syncS(); });
    syncS(); })();
  const radioReq = (scope, greeted, after) => { const w = where(), now = NX().now(), first = !window.__radBr && !after; window.__radBr = 1;  // перший вихід в ефір: одне зведення «місцевість → область → Україна»
    return fetch('/api/radio?scope=' + scope + '&radius=' + (LS.get('radio_radius') || 25) + '&sid=' + radioSid + '&t=' + Math.round(radioSeen || (now - 1800)) + '&obl=' + encodeURIComponent(w.obl) +
      (w.lat != null ? '&lat=' + w.lat + '&lon=' + w.lon : '') + (greeted ? '&g=1' : '') + (after ? '&a=1' : '') + (first ? '&b=1' : '')).then(r => r.json()); };
  async function radioIssue(force, pre) {
    if (!radioOn || playing || radioBusy) return;
    const w = where();
    const now = NX().now();
    const mode = LS.get('radio_scope') || 'near';
    const scope = force === 'country' ? 'country' : mode;
    radioBusy = true;
    try {
      const r = pre ? await pre : await radioReq(scope, false, scope === 'country' && mode !== 'country');  // «Далі головні зміни по Україні»
      if (scope === 'country' || r.kind === 'brief') lastCountry = now;
      if (!radioOn) return;
      // 04.11 власник: новин і змін немає — радіо, як і ефір, вимикається само (через 10 хв без жодного оновлення)
      // 04.11 власник: радіо не вимикається, поки є тривога в області або цілі до 300 км; лише 15 хв повного затишшя → вимкнення
      if (!r.idle) idleSince = 0; else if (!idleSince) idleSince = NX().now();
      if (!r.text || r.level === 'calm') {
        if (idleSince && NX().now() - idleSince > 900 && !radioBusy2) {
          radioBusy2 = true; await SND.outro(); await speak('Нових змін біля вас немає. Вимикаю Скай Радіо.', 'radio'); radioBusy2 = false;
          if (radioOn) rbtn.click();
          return;
        }
        if (!r.text) return;  // нового немає: мовчимо
      } else radioLast = NX().now();
      if (scope === 'near') radioSeen = NX().now();
      const hard = r.level === 'urgent' || r.level === 'outage' || r.kind === 'correction';
      if (hard) bedStop(); else bedStart();  // важливе, виправлення, збій — без фону
      if (r.level === 'urgent' && window.SKYVOICE) window.SKYVOICE.stop();  // важливе перериває поточне
      const sp = r.speech || r.text || '', vp = r.voice || (r.audio ? preUrl(r.audio) : preVoice(sp, 'radio'));  // голос генерується, поки грає сигнал
      await (r.level === 'urgent' ? SND.urgent() : r.level === 'outage' ? SND.outage() : r.level === 'calm' ? SND.calm() : SND.news());
      duck(true); await speak(sp, 'radio', vp); duck(false);
      if (scope === 'country' && !hard) await SND.outro();
    } catch (e) { duck(false); } finally { radioBusy = false; }
  }
  const rbtn = document.createElement('button'); rbtn.id = 'radio-btn'; rbtn.title = 'Sky Radio: голосом про те, що біля вас, щойно щось змінюється; коротко про всю Україну';
  // лише кнопка-значок без тексту на мапі (власник 03.11: «текст не потрібен»)
  const rshow = () => { rbtn.classList.toggle('on', radioOn); rbtn.innerHTML = '<span class=ri>📻</span><span class=rl>Sky Radio</span>'; rbtn.setAttribute('aria-label', radioOn ? 'Sky Radio в ефірі, вимкнути' : 'Увімкнути Sky Radio'); };
  rshow(); document.body.appendChild(rbtn);
  // під рядком лічильників цілей (він може перенестись у два рядки), щоб нічого не перекривати
  // варіант А (власник 03.11): Ефір і Радіо в одному ряду з «Що зараз?» у картці «Мій дім»; без картки — зліва вгорі
  const row = document.getElementById('ai-row');
  const mh = document.querySelector('#me .me-head');
  if (row) { if (mh) { btn.classList.add('in-head'); mh.insertBefore(btn, document.getElementById('me-share') || null); } else row.appendChild(btn); row.appendChild(rbtn); }  // 07.11: Ефір — прямо в смузі картки
  else {
    const place = () => { const c = document.getElementById('counters'); const b = c && c.getBoundingClientRect();
      const y = b && b.height ? Math.round(b.bottom + 8) : 60; rbtn.style.top = y + 'px'; btn.style.top = (y + 48) + 'px'; };
    addEventListener('resize', place); setInterval(place, 3000); place();
  }
  // Ефір: сірий і без світла, поки не активний; відкрито — червона точка світиться (власник 04.11)
  const syncOn = () => btn.classList.toggle('on', !box.hidden);
  try { new MutationObserver(syncOn).observe(box, { attributes: true, attributeFilter: ['hidden'] }); } catch (e) {}
  syncOn();

  const rsay = () => {};
  rbtn.onclick = async () => {
    radioOn = !radioOn; rshow();
    if (!radioOn) { clearInterval(radioT); radioT = null; if (abortAudio) abortAudio(); window.SKYVOICE && window.SKYVOICE.stop(); window.SKYRADIO && window.SKYRADIO.stop(); return; }
    if (playing) { stop = true; try { abortAudio && abortAudio(); window.SKYVOICE && window.SKYVOICE.stop(); } catch (e) {} box.hidden = true; playing = false; }  // Ефір вимикається, коли вмикається Sky Radio
    audioOn = true; LS.set('live_audio', '1'); $('#lv-audio').classList.add('on');
    raCtx();  // звук розблоковується саме цим дотиком (iPhone)
    try { if ('wakeLock' in navigator) await navigator.wakeLock.request('screen'); } catch (e) {}
    radioSeen = seen || (NX().now() - 1800); radioSid = Math.random().toString(36).slice(2, 12); lastCountry = 0; idleSince = 0; radioLast = NX().now();
    // швидкий старт (04.11): випуск і його голос замовляються одразу; позивний і привітання (готовий записаний голос) грають, поки вони готуються
    const sc0 = LS.get('radio_scope') || 'near';
    const pre = radioReq(sc0, true).then(r => { if (r && (r.speech || r.text) && r.level !== 'calm') r.voice = r.audio ? preUrl(r.audio) : preVoice(r.speech || r.text, 'radio'); return r; }).catch(() => ({}));
    await Promise.race([sLoad(), wait(900)]);
    if ((LS.get('radio_mode') || 'music') === 'music' && window.SKYRADIO && window.SKYRADIO.enabled()) {
      await window.SKYRADIO.start();  // готовий джингл → музика; голосовий випуск після джинглу
      for (let w = 0; w < 160 && window.SKYRADIO.state() === 'PLAYING_JINGLE'; w++) await wait(125);
    } else {
      const id = SND.ident();
      const IDT = 'Скай. Розумій, що відбувається в небі.';  // фірмова заставка (специфікація радіо), озвучена один раз і з кешу
      const hi = preVoice(IDT, 'radio');
      await id; await speak(IDT, 'radio', hi);
    }
    await radioIssue(null, pre);         // зведення в обраному режимі охоплення
    // 04.11 власник: «де зведення по Україні?» — за концепцією: на початку й раз на 15 хв, у будь-якому режимі (із заготовок, безкоштовно)
    if (radioOn && sc0 !== 'country' && !lastCountry) await radioIssue('country');
    // «Поруч зі мною» на заготовках дешеве й миттєве — перевіряємо кожні 15 с; область і Україна (через модель) — раз на 40 с
    let tick = 0; radioT = setInterval(() => { tick++; const md = LS.get('radio_scope') || 'near';
      if (md !== 'country' && NX().now() - lastCountry > 900) radioIssue('country');
      else if (md === 'near' || tick % 3 === 0) radioIssue(); }, 15000);
  };

  // ---------- повернення після відсутності: запропонувати ефір
  // повернення після відсутності: жодних вікон поверх мапи (власник 03.11), лише підпис на кнопці «Ефір»
  function offer() {
    if (!NX() || playing || !box.hidden) return;
    const gap = NX().now() - seen;
    if (!seen || gap < 300) return;
    btn.classList.add('new'); btn.querySelector('small').textContent = 'що змінилось за ' + Math.round(gap / 60) + ' хв';
    setTimeout(() => { btn.classList.remove('new'); btn.querySelector('small').textContent = 'що змінилось'; }, 60000);
  }
  document.addEventListener('visibilitychange', () => { if (!document.hidden) setTimeout(offer, 1500); else markSeen(); });
  setTimeout(offer, 4000);
})();
