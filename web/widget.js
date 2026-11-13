/* Налаштування віджета SKY для Windows і міні-вікна (04.11): що показувати, тема, прозорість, розмір тексту, компактний вигляд.
   Діє лише в міні-режимі (?mini=1, віджет Windows і «картинка в картинці»). Зберігається на пристрої. Розмір вікна, кут екрана,
   «поверх усіх вікон» і автозапуск - у меню значка біля годинника (їх задає сама програма Windows). */
(function () {
  'use strict';
  if (!new URLSearchParams(location.search).has('mini') && !document.body.classList.contains('mini')) return;
  const KEY = 'wcfg';
  const DEF = { theme: 'auto', alpha: 1, fs: 1, list: true, ai: true, counts: false, map: false, compact: false };
  let C = Object.assign({}, DEF);
  try { Object.assign(C, JSON.parse(localStorage.getItem(KEY) || '{}')); } catch (e) {}
  const save = () => { try { localStorage.setItem(KEY, JSON.stringify(C)); } catch (e) {} };

  const st = document.createElement('style');
  st.textContent = `
  body.mini{background:rgba(7,9,14,var(--wa,1))!important}
  body.mini .me{background:rgba(16,20,30,calc(var(--wa,1)*.92))!important;zoom:var(--wfs,1)}
  body.mini.w-nolist .me-list,body.mini.w-noai .ai-box{display:none!important}
  body.mini.w-compact .me-sub,body.mini.w-compact .me-list,body.mini.w-compact .ai-box,body.mini.w-compact .fc{display:none!important}
  body.mini.w-counts .top{display:flex!important;left:8px;right:8px;top:auto;bottom:8px;zoom:.7}
  body.mini.w-map #map{visibility:visible}
  body.mini.w-map .me{top:auto!important;bottom:8px!important;max-height:55%}
  #w-gear{position:fixed;top:10px;right:10px;z-index:90;width:30px;height:30px;border-radius:50%;border:1px solid rgba(255,255,255,.25);
    background:rgba(20,24,34,.85);color:#fff;font-size:15px;line-height:28px;text-align:center;padding:0;cursor:pointer}
  #w-panel{position:fixed;inset:8px;z-index:91;background:#0f131c;color:#e8edf5;border:1px solid rgba(255,255,255,.18);border-radius:14px;
    padding:12px 14px;overflow:auto;font:13px/1.4 system-ui,sans-serif}
  #w-panel h4{margin:0 0 8px;font-size:14px}#w-panel .r{display:flex;align-items:center;gap:8px;margin:8px 0;flex-wrap:wrap}
  #w-panel .r>span{min-width:96px;opacity:.7}
  #w-panel .seg button{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.2);color:#fff;border-radius:999px;padding:4px 10px;font:600 12px system-ui;margin-right:4px}
  #w-panel .seg button.on{background:rgba(120,160,255,.3);border-color:rgba(150,180,255,.7)}
  #w-panel label{display:flex;gap:8px;align-items:center;margin:6px 0}
  #w-panel .note{opacity:.6;font-size:11.5px;margin-top:10px}
  #w-panel .x{position:absolute;top:8px;right:10px;background:none;border:0;color:#fff;font-size:18px}`;
  document.head.appendChild(st);

  function apply() {
    const b = document.body, r = document.documentElement;
    r.style.setProperty('--wa', C.alpha);
    r.style.setProperty('--wfs', C.fs);
    b.classList.toggle('w-nolist', !C.list);
    b.classList.toggle('w-noai', !C.ai);
    b.classList.toggle('w-compact', !!C.compact);
    b.classList.toggle('w-counts', !!C.counts);
    b.classList.toggle('w-map', !!C.map);
    const want = C.theme === 'light' ? 'day' : C.theme === 'dark' ? 'night' : null;
    if (want && r.dataset.theme !== want) r.dataset.theme = want;
    if (C.map && window.NX && NX().map && NX().map()) setTimeout(() => { try { NX().map().resize(); } catch (e) {} }, 50);
  }

  const seg = (k, opts) => '<span class="seg" data-k="' + k + '">' + opts.map(([v, l]) => '<button data-v="' + v + '"' + (String(C[k]) === String(v) ? ' class="on"' : '') + '>' + l + '</button>').join('') + '</span>';
  const chk = (k, l) => '<label><input type="checkbox" data-c="' + k + '"' + (C[k] ? ' checked' : '') + '>' + l + '</label>';

  const gear = document.createElement('button');
  gear.id = 'w-gear'; gear.textContent = '⚙'; gear.title = 'Налаштування віджета';
  document.body.appendChild(gear);
  let panel = null;
  gear.onclick = () => {
    if (panel) { panel.remove(); panel = null; return; }
    panel = document.createElement('div'); panel.id = 'w-panel';
    panel.innerHTML = '<button class="x" aria-label="Закрити">✕</button><h4>Налаштування віджета</h4>' +
      '<div class="r"><span>Тема</span>' + seg('theme', [['auto', 'як у системі'], ['dark', 'темна'], ['light', 'світла']]) + '</div>' +
      '<div class="r"><span>Прозорість фону</span>' + seg('alpha', [[1, '0%'], [0.85, '15%'], [0.7, '30%'], [0.55, '45%']]) + '</div>' +
      '<div class="r"><span>Розмір тексту</span>' + seg('fs', [[0.85, 'менший'], [1, 'звичайний'], [1.15, 'більший'], [1.3, 'великий']]) + '</div>' +
      '<div class="r"><span>Показувати</span></div>' +
      chk('compact', 'Лише головний рядок («Над вами чисто» / хвилини до загрози)') +
      chk('list', 'Список цілей біля вас') + chk('ai', 'Кнопки «Що зараз?», Ефір і Sky Radio') +
      chk('counts', 'Лічильники цілей по Україні') + chk('map', 'Маленьку мапу') +
      '<p class="note">Розмір вікна, кут екрана, «поверх усіх вікон» і запуск разом з Windows: правою кнопкою на значку SKY біля годинника. ' +
      'Звук і голос: у повній версії SKY → «Ще» → «Звук».</p>';
    document.body.appendChild(panel);
    panel.querySelector('.x').onclick = () => { panel.remove(); panel = null; };
    panel.querySelectorAll('.seg button').forEach(b => b.onclick = () => {
      const k = b.parentNode.dataset.k, v = b.dataset.v;
      C[k] = isNaN(+v) ? v : +v; save(); apply();
      b.parentNode.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
    });
    panel.querySelectorAll('input[data-c]').forEach(i => i.onchange = () => { C[i.dataset.c] = i.checked; save(); apply(); });
  };
  // повна версія сама перемикає день/ніч - у віджеті перевага за вибором власника
  try { new MutationObserver(() => { if (C.theme !== 'auto') apply(); }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] }); } catch (e) {}
  apply();
})();
