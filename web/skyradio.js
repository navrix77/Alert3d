/* SKY RADIO · аудіодвижок 1.0: готова музика + готовий джингл, канали MUSIC / JINGLE / MASTER, дакінг, пріоритети.
   Стани: IDLE, STARTING, PLAYING_JINGLE, PLAYING_MUSIC, PAUSED, INTERRUPTED, ERROR. Без сторонніх бібліотек. */
(function () {
  'use strict';
  const FILES = { music: '/audio/sky-radio/music.mp3', jingle: '/audio/sky-radio/jingle.mp3' };
  const DEF = { musicEnabled: true, jingleEnabled: true, jingleIntervalMinutes: 15, masterVolume: 0.35, musicDuckDb: -18, fadeOutMs: 350, fadeInMs: 800, pauseOnCriticalAlert: true };
  const LSK = 'skyradio_cfg';
  let cfg = Object.assign({}, DEF);
  try { cfg = Object.assign(cfg, JSON.parse(localStorage.getItem(LSK) || '{}')); } catch (e) {}
  const save = () => { try { localStorage.setItem(LSK, JSON.stringify(cfg)); } catch (e) {} };
  const db = x => Math.pow(10, x / 20);
  const TAB = Math.random().toString(36).slice(2);
  let ctx, music, jingle, mG, jG, master, ana, state = 'IDLE', muted = false, activeSec = 0, tick = null, voiceDuck = false, critical = 0,
      musicWanted = false, jingleBusy = false, jPending = false, bc = null, ui = {};
  const subs = new Set();
  function setState(s) { if (state === s) return; state = s; subs.forEach(f => { try { f(s); } catch (e) {} }); render(); }
  function ramp(g, v, ms) { try { const t = ctx.currentTime; g.gain.cancelScheduledValues(t); g.gain.setValueAtTime(g.gain.value, t); g.gain.linearRampToValueAtTime(v, t + Math.max(0.02, ms / 1000)); } catch (e) {} }
  const workLevel = () => 1;
  const duckLevel = () => db(cfg.musicDuckDb);
  function build() {
    if (ctx) return true;
    try {
      const C = window.AudioContext || window.webkitAudioContext; ctx = new C();
      music = new Audio(FILES.music); jingle = new Audio(FILES.jingle);
      [music, jingle].forEach(a => { a.preload = 'auto'; a.crossOrigin = 'anonymous'; a.setAttribute('playsinline', ''); });
      music.loop = true;
      mG = ctx.createGain(); jG = ctx.createGain(); master = ctx.createGain(); ana = ctx.createAnalyser(); ana.fftSize = 64;
      const lim = ctx.createDynamicsCompressor(); lim.threshold.value = -3; lim.knee.value = 0; lim.ratio.value = 20; lim.attack.value = 0.003; lim.release.value = 0.25;
      ctx.createMediaElementSource(music).connect(mG); ctx.createMediaElementSource(jingle).connect(jG);
      mG.connect(master); jG.connect(master); master.connect(lim); lim.connect(ana); ana.connect(ctx.destination);
      mG.gain.value = 0.0001; jG.gain.value = 1; master.gain.value = muted ? 0 : cfg.masterVolume;
      [music, jingle].forEach(a => a.addEventListener('error', () => { if (state !== 'IDLE') { setState('ERROR'); toast('SKY RADIO: не вдалося завантажити аудіо'); } }));
      music.addEventListener('pause', () => { if (musicWanted && !critical && state !== 'PAUSED' && state !== 'IDLE') setState('INTERRUPTED'); });  // системне переривання (дзвінок, Siri)
      jingle.addEventListener('ended', onJingleEnd);
      if ('BroadcastChannel' in window) { bc = new BroadcastChannel('skyradio'); bc.onmessage = e => { if (e.data && e.data.t === 'start' && e.data.id !== TAB && musicWanted) pause(true); }; }
      mediaSession();
      return true;
    } catch (e) { setState('ERROR'); return false; }
  }
  function mediaSession() { try { if (!('mediaSession' in navigator)) return;
    navigator.mediaSession.metadata = new MediaMetadata({ title: 'SKY RADIO', artist: 'NAVRYX SKY', album: 'Ефір' });
    navigator.mediaSession.setActionHandler('play', () => start()); navigator.mediaSession.setActionHandler('pause', () => pause()); } catch (e) {} }
  async function resumeCtx() { try { if (ctx.state !== 'running') await ctx.resume(); } catch (e) {} return ctx.state === 'running'; }
  async function start() {
    if (!cfg.musicEnabled) return false;
    if (!build()) return false;
    if (state === 'PLAYING_MUSIC' || state === 'PLAYING_JINGLE' || state === 'STARTING') return true;
    setState('STARTING'); critical = 0; musicWanted = true;
    try { bc && bc.postMessage({ t: 'start', id: TAB }); } catch (e) {}
    if (!(await resumeCtx())) { setState('ERROR'); toast('SKY RADIO: браузер не дозволив звук, натисніть ще раз'); musicWanted = false; return false; }
    try {
      mG.gain.value = duckLevel();               // музика стартує приглушеною
      await music.play();
    } catch (e) { musicWanted = false; setState('ERROR'); toast('SKY RADIO: відтворення заблоковано браузером'); return false; }
    activeSec = 0; startTick();
    if (cfg.jingleEnabled) await playJingle(true); else { ramp(mG, workLevel(), cfg.fadeInMs); setState('PLAYING_MUSIC'); }
    return true;
  }
  async function playJingle(first) {
    if (jingleBusy || !musicWanted || critical) return;
    if (voiceDuck) { jPending = true; return; }
    jingleBusy = true; jPending = false;
    if (!first) { ramp(mG, duckLevel(), cfg.fadeOutMs); await new Promise(r => setTimeout(r, cfg.fadeOutMs)); }
    if (!musicWanted || critical) { jingleBusy = false; return; }
    try { jingle.currentTime = 0; setState('PLAYING_JINGLE'); await jingle.play(); }
    catch (e) { jingleBusy = false; ramp(mG, workLevel(), cfg.fadeInMs); setState('PLAYING_MUSIC'); }
  }
  function onJingleEnd() { jingleBusy = false; activeSec = 0; if (!musicWanted || critical) return; ramp(mG, voiceDuck ? duckLevel() : workLevel(), cfg.fadeInMs); setState('PLAYING_MUSIC'); }
  function startTick() { clearInterval(tick); tick = setInterval(() => {
    if (state !== 'PLAYING_MUSIC' || document.hidden === undefined) { return; }
    activeSec++;
    if (cfg.jingleEnabled && activeSec >= cfg.jingleIntervalMinutes * 60) { activeSec = 0; playJingle(false); }
    if (jPending && !voiceDuck) playJingle(false);
  }, 1000); }
  function pause(silent) {
    if (!ctx || state === 'IDLE') return;
    musicWanted = false; jPending = false; jingleBusy = false; clearInterval(tick);
    try { ramp(mG, 0.0001, 150); setTimeout(() => { if (!musicWanted) { music.pause(); jingle.pause(); } }, 180); } catch (e) {}
    setState(silent ? 'PAUSED' : 'PAUSED');
  }
  function stop() { pause(); setTimeout(() => setState('IDLE'), 220); }
  async function resume() { if (state === 'PLAYING_MUSIC' || state === 'PLAYING_JINGLE') return; critical = 0; hideResume(); musicWanted = true;
    if (!(await resumeCtx())) return setState('ERROR');
    try { await music.play(); ramp(mG, workLevel(), cfg.fadeInMs); startTick(); setState('PLAYING_MUSIC'); } catch (e) { musicWanted = false; setState('ERROR'); } }
  // пріоритети: 1) критичні сповіщення, 2) інформаційний голос (дакінг), 3) джингл, 4) музика
  function duck(on) { voiceDuck = !!on; if (!ctx || !musicWanted || critical) return; ramp(mG, on ? duckLevel() : (state === 'PLAYING_JINGLE' ? duckLevel() : workLevel()), on ? cfg.fadeOutMs : cfg.fadeInMs); }
  window.addEventListener('sky-alert', e => {
    if (!ctx || !cfg.pauseOnCriticalAlert) return;
    if (e.detail && e.detail.on) { if (!musicWanted && state !== 'PLAYING_MUSIC' && state !== 'PLAYING_JINGLE') return; critical++; musicWanted = false; jPending = false; jingleBusy = false; clearInterval(tick); try { ramp(mG, 0.0001, 80); setTimeout(() => { music.pause(); jingle.pause(); }, 100); } catch (x) {} setState('INTERRUPTED'); }
    else if (critical) { critical = Math.max(0, critical - 1); if (!critical && state === 'INTERRUPTED') showResume(); }
  });
  document.addEventListener('visibilitychange', () => { if (!document.hidden && ctx && musicWanted && ctx.state === 'suspended') ctx.resume().catch(() => {}); });
  // ---------- інтерфейс ----------
  function toast(m) { try { const t = document.getElementById('toast'); if (t) { t.textContent = m; t.classList.add('on'); setTimeout(() => t.classList.remove('on'), 3500); } } catch (e) {} }
  function showResume() { if (ui.res) ui.res.hidden = false; }
  function hideResume() { if (ui.res) ui.res.hidden = true; }
  function mkUI() {
    if (ui.bar) return;
    const st = document.createElement('style');
    st.textContent = '#skr{position:fixed;left:50%;transform:translateX(-50%);top:calc(env(safe-area-inset-top) + 8px);z-index:36;display:flex;align-items:center;gap:8px;padding:6px 10px;border-radius:999px;background:rgba(14,18,28,.82);-webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px);border:1px solid rgba(255,255,255,.14);color:#E8ECF4;font:600 12px system-ui;max-width:94vw}#skr[hidden]{display:none}#skr button{min-width:44px;min-height:44px;border:0;border-radius:50%;background:rgba(255,255,255,.08);color:#fff;font-size:16px}#skr button:focus-visible,#skr input:focus-visible{outline:2px solid #8fb4ff;outline-offset:2px}#skr .nm{letter-spacing:.08em}#skr .dot{width:8px;height:8px;border-radius:50%;background:#667}#skr.on .dot{background:#3be07a;box-shadow:0 0 8px #3be07a}#skr.jg .dot{background:#FFB020;box-shadow:0 0 8px #FFB020}#skr.er .dot{background:#FF4D4D}#skr canvas{width:34px;height:20px}#skr input[type=range]{width:70px}#skr .jt{display:none;color:#FFB020}#skr.jg .jt{display:inline}#skr-set{position:fixed;left:50%;transform:translateX(-50%);top:calc(env(safe-area-inset-top) + 64px);z-index:37;width:min(92vw,340px);padding:14px;border-radius:16px;background:rgba(14,18,28,.95);border:1px solid rgba(255,255,255,.14);color:#E8ECF4;font:14px system-ui}#skr-set[hidden],#skr-res[hidden]{display:none}#skr-set label{display:flex;justify-content:space-between;align-items:center;gap:10px;margin:8px 0;min-height:36px}#skr-set select,#skr-set button{min-height:40px;border-radius:10px;border:1px solid rgba(255,255,255,.2);background:#1b2233;color:#fff;padding:0 10px}#skr-res{position:fixed;left:50%;transform:translateX(-50%);top:calc(env(safe-area-inset-top) + 64px);z-index:37;padding:10px 16px;min-height:44px;border-radius:999px;border:1px solid #FFB020;background:rgba(14,18,28,.95);color:#FFB020;font:700 14px system-ui}';
    document.head.appendChild(st);
    const bar = document.createElement('div'); bar.id = 'skr'; bar.hidden = true; bar.setAttribute('role', 'region'); bar.setAttribute('aria-label', 'SKY RADIO');
    bar.innerHTML = '<button id="skr-pp" aria-label="Пауза">⏸</button><span class="dot" aria-hidden="true"></span><span class="nm">SKY RADIO</span><span class="jt">джингл</span><canvas id="skr-v" width="34" height="20" aria-hidden="true"></canvas><button id="skr-mu" aria-label="Вимкнути звук">🔊</button><input id="skr-vol" type="range" min="0" max="100" aria-label="Гучність SKY RADIO"><button id="skr-gr" aria-label="Налаштування SKY RADIO">⚙</button>';
    document.body.appendChild(bar);
    const set = document.createElement('div'); set.id = 'skr-set'; set.hidden = true;
    set.innerHTML = '<label>Музика<input type="checkbox" id="skr-me"></label><label>Джингл<input type="checkbox" id="skr-je"></label><label>Інтервал джинглу<select id="skr-iv"><option>10</option><option>15</option><option>20</option><option>30</option></select></label><label>Пауза при критичній тривозі<input type="checkbox" id="skr-pc"></label><label>Джингл зараз<button id="skr-jn">▶</button></label>';
    document.body.appendChild(set);
    const res = document.createElement('button'); res.id = 'skr-res'; res.hidden = true; res.textContent = 'Тривога минула · відновити ефір'; document.body.appendChild(res);
    ui = { bar, set, res, pp: bar.querySelector('#skr-pp'), mu: bar.querySelector('#skr-mu'), vol: bar.querySelector('#skr-vol'), cv: bar.querySelector('#skr-v') };
    ui.pp.onclick = () => { if (state === 'PLAYING_MUSIC' || state === 'PLAYING_JINGLE' || state === 'STARTING') pause(); else if (state === 'INTERRUPTED' || state === 'PAUSED') resume(); else start(); };
    ui.mu.onclick = () => { muted = !muted; if (master) ramp(master, muted ? 0 : cfg.masterVolume, 120); render(); };
    ui.vol.value = Math.round(cfg.masterVolume * 100);
    ui.vol.oninput = () => { cfg.masterVolume = ui.vol.value / 100; muted = false; if (master) ramp(master, cfg.masterVolume, 80); save(); render(); };
    bar.querySelector('#skr-gr').onclick = () => { set.hidden = !set.hidden; };
    const me = set.querySelector('#skr-me'), je = set.querySelector('#skr-je'), iv = set.querySelector('#skr-iv'), pc = set.querySelector('#skr-pc');
    me.checked = cfg.musicEnabled; je.checked = cfg.jingleEnabled; iv.value = String(cfg.jingleIntervalMinutes); pc.checked = cfg.pauseOnCriticalAlert;
    me.onchange = () => { cfg.musicEnabled = me.checked; save(); if (!me.checked) stop(); };
    je.onchange = () => { cfg.jingleEnabled = je.checked; save(); };
    iv.onchange = () => { cfg.jingleIntervalMinutes = +iv.value; save(); };
    pc.onchange = () => { cfg.pauseOnCriticalAlert = pc.checked; save(); };
    set.querySelector('#skr-jn').onclick = () => { if (state === 'PLAYING_MUSIC') playJingle(false); };
    res.onclick = () => resume();
    anim();
  }
  function render() {
    if (!ui.bar) return;
    const on = state === 'PLAYING_MUSIC' || state === 'PLAYING_JINGLE' || state === 'STARTING';
    ui.bar.hidden = state === 'IDLE';
    ui.bar.className = state === 'PLAYING_JINGLE' ? 'jg' : (state === 'ERROR' ? 'er' : (on ? 'on' : ''));
    ui.bar.id = 'skr';
    ui.pp.textContent = on ? '⏸' : '▶'; ui.pp.setAttribute('aria-label', on ? 'Пауза' : 'Грати');
    ui.mu.textContent = (muted || cfg.masterVolume === 0) ? '🔇' : '🔊'; ui.mu.setAttribute('aria-label', muted ? 'Увімкнути звук' : 'Вимкнути звук');
    if (state === 'INTERRUPTED' && !critical) { /* системне переривання: кнопка ▶ відновить */ }
  }
  function anim() { const c = ui.cv.getContext('2d'), d = new Uint8Array(32);
    let lt = 0; const f = (t) => { requestAnimationFrame(f); if (document.hidden || ui.bar.hidden || !ana || t - lt < 50) return; lt = t; ana.getByteFrequencyData(d); c.clearRect(0, 0, 34, 20); c.fillStyle = state === 'PLAYING_JINGLE' ? '#FFB020' : '#8fb4ff';
      for (let i = 0; i < 6; i++) { const v = d[i * 2 + 1] / 255, h = Math.max(2, v * 20); c.fillRect(i * 6, 20 - h, 4, h); } };
    f(); }
  const api = { start: async () => { mkUI(); return start(); }, stop, pause: () => pause(), resume, duck, jingleNow: () => { if (state === 'PLAYING_MUSIC') playJingle(false); },
    state: () => state, config: () => Object.assign({}, cfg), setConfig: (k, v) => { cfg[k] = v; save(); }, onState: f => subs.add(f), enabled: () => cfg.musicEnabled, _t: () => ({ activeSec, critical, voiceDuck }) };
  window.SKYRADIO = api;
  if (document.readyState !== 'loading') mkUI(); else document.addEventListener('DOMContentLoaded', mkUI);
})();
