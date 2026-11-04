/* Єдиний генератор символів тактичного режиму SKY за NATO APP-6(E) Version 1.
 *
 * Кодування: 30-цифровий SIDC (версія «13» = APP-6 Edition E у milsymbol 3.0.5, MIT; бібліотека лежить у /vendor/milsymbol.js).
 * Символи малює лише ця бібліотека за SIDC. Власних рамок, кольорів і значків немає.
 *
 * Розподіл відповідальності:
 *  - у символ потрапляє тільки те, що передбачено стандартом: належність (рамка), набір і тип об'єкта (внутрішній знак),
 *    кількість (поле C), напрямок руху (індикатор), тип/модель (поле, яке малює мапа як текст);
 *  - власні дані SKY (джерело, час повідомлення, точність місця, статус оцінки, «застаріло») символ НЕ змінюють:
 *    вони йдуть окремими полями інтерфейсу (sky()). Статус символу завжди «present» (0): оцінка місця, давність і невідомий
 *    тип не виражаються статусом «planned/anticipated»; «невідомий тип» ≠ «невідома належність»; «застаріле» ≠ «знищено».
 *
 * Це символіка за APP-6, а не сертифікація НАТО.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(require('./vendor/milsymbol.js'));
  else root.App06 = factory(root.ms);
})(typeof self !== 'undefined' ? self : this, function (msLib) {
  const ms = (msLib && msLib.Symbol) ? msLib : (msLib && msLib.ms) || msLib;
  const EDITION = { standard: 'NATO APP-6', edition: 'E', version: 1, sidcVersion: '13', sidcLength: 30, lib: 'milsymbol 3.0.5 (MIT)' };

  // Належність (позиція 4 SIDC)
  const AFF = { pending: '0', unknown: '1', assumed: '2', friend: '3', neutral: '4', suspect: '5', hostile: '6' };
  const AFF_NAME = { '0': 'Pending', '1': 'Unknown', '2': 'Assumed friend', '3': 'Friend', '4': 'Neutral', '5': 'Suspect', '6': 'Hostile' };
  const AFF_UA = { '0': 'Не визначено', '1': 'Невідома', '2': 'Імовірно своя', '3': 'Своя', '4': 'Нейтральна', '5': 'Підозрювана', '6': 'Ворожа' };
  const SETS = { '01': 'Air', '02': 'Air missile', '10': 'Land unit', '20': 'Land installation' };
  const DIM = { '01': 'Air', '02': 'Air', '10': 'Ground', '20': 'Ground' };

  // Відповідність типів SKY стандартним кодам: набір (symbol set), сутність (6 цифр), модифікатор 1 і 2.
  // exact=false: у стандарті немає точнішої сутності, взято найближчу батьківську, а конкретика йде текстовим полем.
  const E = (set, ent, m1, m2, std, exact, note) => ({ set, entity: ent, m1: m1 || '00', m2: m2 || '00', std, exact, note: note || '' });
  const UAV = (note, m1, std) => E('01', '110300', m1, '00', std || 'Air / Military / Unmanned aerial vehicle (UAV)', true, note);
  const MAP = {
    shahed: UAV('Дрон-камікадзе: у стандарті окремої сутності немає, це клас БпЛА; модель у текстовому полі'),
    geran5: UAV('Реактивний ударний БпЛА: клас БпЛА; модель у полі'),
    jet: UAV('Реактивний БпЛА: клас БпЛА; модель у полі'),
    molniya: UAV('Малий ударний БпЛА: клас БпЛА; модель у полі'),
    fpv: UAV('FPV-дрон: клас БпЛА'),
    fpvf: UAV('FPV на оптоволокні: клас БпЛА; спосіб керування в полі'),
    lancet: UAV('Дрон-камікадзе «Ланцет»: клас БпЛА; модель у полі'),
    recon: UAV('Розвідувальний БпЛА', '18', 'Air / Military / Unmanned aerial vehicle (UAV) / Reconnaissance'),
    cruise: E('02', '110000', '07', '00', 'Air missile / Missile / Cruise', true, 'Крилата ракета'),
    banderol: E('02', '110000', '07', '00', 'Air missile / Missile / Cruise', true, 'Крилата ракета «Бандероль»: той самий символ, назва в полі'),
    ballistic: E('02', '110000', '06', '00', 'Air missile / Missile / Ballistic', true, 'Балістична ракета'),
    kab: E('01', '130100', '00', '00', 'Air / Weapon / Bomb', true, 'Керована авіабомба: у стандарті є лише «Bomb»; «КАБ» у полі'),
    rszv: E('02', '110000', '00', '00', 'Air missile / Missile', false, 'Реактивний снаряд РСЗВ: в APP-6 немає окремої сутності, взято загальну «Missile»'),
    // стратегічна авіація та МіГ-31К (сутність — літак, модель — текстове поле)
    tu95: E('01', '110100', '02', '00', 'Air / Military / Fixed-wing / Bomber', true, 'Ту-95МС'),
    tu160: E('01', '110100', '02', '00', 'Air / Military / Fixed-wing / Bomber', true, 'Ту-160'),
    tu22: E('01', '110100', '02', '00', 'Air / Military / Fixed-wing / Bomber', true, 'Ту-22М3'),
    mig31: E('01', '110100', '00', '00', 'Air / Military / Fixed-wing', false, 'МіГ-31К: роль у повідомленнях не названа, тому загальний «Fixed-wing» без ролі'),
    // об'єкти ворога з DeepState (наземні): установка або підрозділ; сутність лише там, де є точний код, інакше загальний знак
    enemy_airfield: E('20', '120803', '00', '00', 'Land installation / Infrastructure / Military / Airport', true, 'Аеродром (OSM)'),
    enemy_hq: Object.assign(E('10', '000000', '00', '00', 'Land unit / Unspecified (HQ indicator)', false, 'Штаб (OSM): рід військ не відомий, тому загальний підрозділ зі знаком штабу'), { hq: true }),
    enemy_object: E('20', '110000', '00', '00', 'Land installation / Military', false, 'Об\'єкт ворога (OSM): загальна військова установка; назва в полі'),
    // тип невстановлений: загальний повітряний об'єкт; належність при цьому лишається за даними
    unknown: E('01', '000000', '00', '00', 'Air (unspecified)', true, 'Тип не встановлено: порожній внутрішній знак, рамка за належністю'),
  };
  const MODEL = { shahed: 'Шахед', geran5: 'Герань-5', jet: 'Реактивний БпЛА', molniya: 'Молнія', fpv: 'FPV', fpvf: 'FPV (оптоволокно)', lancet: 'Ланцет',
    recon: 'Розвідник', cruise: 'КР', banderol: 'Бандероль', ballistic: 'БР', kab: 'КАБ', rszv: 'РСЗВ', tu95: 'Ту-95МС', tu160: 'Ту-160', tu22: 'Ту-22М3', mig31: 'МіГ-31К', unknown: '', enemy_airfield: 'Аеродром', enemy_hq: 'Штаб', enemy_object: '' };

  const pad = (s, n) => String(s).padStart(n, '0');
  function affiliationOf(d) {
    // належність тільки за даними (не за виглядом): d = {official, indep, idLvl, ai}
    d = d || {};
    if (d.official) return 'hostile';
    if ((d.indep || 0) >= 2 || d.idLvl === 'висока') return 'hostile';
    if (d.ai && (d.indep || 0) < 2) return 'unknown';
    return 'suspect';
  }
  function entryOf(type) { return MAP[type] || MAP.unknown; }
  const q15 = h => ((Math.round(h / 15) * 15) % 360 + 360) % 360;

  // Збирає SIDC: версія 13, контекст 0 (реальність), належність, набір, статус 0, HQ/TF/dummy 0, ешелон/мобільність 00, сутність, M1, M2, решта нулі
  function sidc(type, aff) {
    const en = entryOf(type), a = AFF[aff] != null ? AFF[aff] : AFF.unknown;
    return EDITION.sidcVersion + '0' + a + en.set + '0' + (en.hq ? '2' : '0') + '00' + en.entity + en.m1 + en.m2 + '0000000000';
  }

  // spec: {type, affiliation, hd (градуси або null), count (число або null), mono, size}
  function build(spec) {
    spec = spec || {};
    const en = entryOf(spec.type), id = sidc(spec.type, spec.affiliation || 'unknown');
    const dir = (typeof spec.hd === 'number' && isFinite(spec.hd)) ? q15(spec.hd) : null;      // індикатор лише коли напрямок відомий
    const qty = spec.count > 1 ? String(Math.min(999, Math.round(spec.count))) : '';
    const o = { size: spec.size || 28, outlineColor: 'rgb(8,10,14)', outlineWidth: 3, fill: true, frame: true };
    if (dir != null) o.direction = dir;
    if (qty) o.quantity = qty;
    if (spec.mono) o.monoColor = 'rgb(240,242,245)';
    const key = ['a6', id, dir == null ? 'n' : dir, qty || '-', spec.mono ? 'm' : 'c', o.size].join('|');
    return { sidc: id, entry: en, opts: o, key, dir, qty, model: spec.model != null ? spec.model : (MODEL[spec.type] || ''), aff: spec.affiliation || 'unknown' };
  }
  function symbol(spec) { const b = build(spec); return new ms.Symbol(b.sidc, b.opts); }
  function svg(spec) { return symbol(spec).asSVG(); }

  // Власні поля SKY: НЕ частина символу, SIDC від них не залежить
  function sky(f) {
    f = f || {};
    return { source: f.source || '', reportedAt: f.reportedAt || null, ageS: f.ageS == null ? null : f.ageS, accuracyKm: f.accuracyKm == null ? null : f.accuracyKm,
      estimate: !!f.estimate, stale: !!f.stale };
  }

  // Перевірка символу за правилами: структура SIDC, наявність кодів у таблицях, відповідність відомих даних, чорно-білий вигляд
  function check(spec) {
    const p = [], b = build(spec), s = b.sidc;
    if (!/^\d{30}$/.test(s)) p.push('SIDC не з 30 цифр');
    if (s.slice(0, 2) !== EDITION.sidcVersion) p.push('версія SIDC не 13 (APP-6E)');
    if (s[2] !== '0') p.push('контекст не «реальність»');
    if (!'0123456'.includes(s[3])) p.push('невідома належність');
    if (!SETS[s.slice(4, 6)]) p.push('набір не передбачений (01, 02, 10, 20)');
    if (s[6] !== '0') p.push('статус символу має бути «present»: оцінка/давність не виражаються статусом');
    if (s[7] !== (b.entry.hq ? '2' : '0') || s.slice(8, 10) !== '00') p.push('HQ/TF/dummy і ешелон: дозволено лише індикатор штабу, де він у таблиці');
    if (s.slice(20) !== '0000000000') p.push('невикористані позиції SIDC мають бути нульовими');
    let y;
    try { y = new ms.Symbol(s, b.opts); } catch (e) { p.push('бібліотека не збудувала символ: ' + e.message); return p; }
    const v = y.isValid(true);
    if (!v.icon) p.push('код сутності/модифікаторів відсутній у таблицях стандарту');
    if (!v.drawInstructions) p.push('символ не має повних інструкцій малювання');
    if (v.dimension !== DIM[s.slice(4, 6)]) p.push('вимір символу не відповідає набору: ' + v.dimension);
    const want = { '0': 'Unknown', '1': 'Unknown', '2': 'Friend', '3': 'Friend', '4': 'Neutral', '5': 'Hostile', '6': 'Hostile' }[s[3]];
    if (v.affiliation !== want) p.push('рамка не відповідає належності: ' + v.affiliation + ' ≠ ' + want);
    if (b.dir != null && !(b.opts.direction >= 0 && b.opts.direction < 360)) p.push('некоректний напрямок');
    if (b.dir == null && 'direction' in b.opts) p.push('індикатор напрямку без відомого напрямку');
    // чорно-білий вигляд: без кольору символ лишається зрозумілим (належність видно за формою рамки)
    const mono = new ms.Symbol(s, Object.assign({}, b.opts, { monoColor: 'rgb(240,242,245)' })).asSVG();
    const cols = (mono.match(/(?:fill|stroke)="[^"]*"/g) || []).map(x => x.replace(/^[a-z]+="|"$/g, '')).filter(c => c !== 'none');
    for (const c of cols) { const m = c.match(/\d+(?:\.\d+)?/g) || []; const v = m.slice(0, 3).map(Number); if (c === 'black' || c === 'white') continue;
      if (v.length < 3 || Math.max(...v) - Math.min(...v) > 12) { p.push('чорно-білий вигляд містить колір: ' + c); break; } }
    return p;
  }

  // Рядки для легенди й таблиці відповідності
  function table() {
    return Object.keys(MAP).map(t => ({ type: t, model: MODEL[t], set: MAP[t].set, entity: MAP[t].entity, m1: MAP[t].m1, m2: MAP[t].m2, std: MAP[t].std, exact: MAP[t].exact, note: MAP[t].note,
      sidc: sidc(t, 'hostile') }));
  }
  function affiliations() { return ['unknown', 'suspect', 'hostile'].map(a => ({ aff: a, code: AFF[a], name: AFF_NAME[AFF[a]], ua: AFF_UA[AFF[a]] })); }

  return { EDITION, AFF, AFF_NAME, AFF_UA, MAP, MODEL, affiliationOf, entryOf, sidc, build, symbol, svg, sky, check, table, affiliations, q15 };
});
