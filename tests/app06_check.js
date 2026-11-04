// Перевірка символів тактичного режиму за APP-6(E): кожен тип × належність × сценарії. Вихід ≠ 0, якщо є порушення.
const A = require('../web/app06.js');
const bad = [];
const fail = (m) => bad.push(m);
const types = Object.keys(A.MAP);
const affs = ['unknown', 'suspect', 'hostile'];
let n = 0;
for (const t of types) for (const a of affs) for (const hd of [null, 0, 47, 359.9]) for (const count of [null, 1, 6]) {
  n++; const p = A.check({ type: t, affiliation: a, hd, count });
  p.forEach(x => fail(`${t}/${a}/hd=${hd}/n=${count}: ${x}`));
}
// наземні об'єкти ворога: HQ лише з індикатором штабу, кожен варіант проходить перевірку
for (const t of ['enemy_airfield', 'enemy_hq', 'enemy_object']) for (const a of ['suspect', 'hostile']) { A.check({ type: t, affiliation: a }).forEach(x => fail(`${t}/${a}: ${x}`)); n++; }
// невідомий або відсутній тип: загальний повітряний об'єкт, належність не змінюється
for (const t of [undefined, null, 'щось-нове']) for (const a of affs) {
  const s = A.sidc(t, a); if (s.slice(10, 16) !== '000000') fail('невідомий тип має давати сутність 000000: ' + t);
  if (s[3] !== A.AFF[a]) fail('невідомий тип змінив належність: ' + t + '/' + a);
  A.check({ type: t, affiliation: a }).forEach(x => fail(`unknown-type ${t}/${a}: ${x}`)); n++;
}
// невідома належність не залежить від типу, а невідомий тип не залежить від належності
for (const t of types) { const s = A.sidc(t, 'unknown'); if (s[3] !== '1') fail('належність unknown підмінена для ' + t); }
// відсутні дані: без напрямку немає індикатора, без кількості немає поля C
{ const b = A.build({ type: 'shahed', affiliation: 'suspect', hd: null, count: null }); if ('direction' in b.opts || 'quantity' in b.opts) fail('поля без даних'); }
{ const b = A.build({ type: 'shahed', affiliation: 'suspect', hd: NaN, count: 0 }); if ('direction' in b.opts || 'quantity' in b.opts) fail('NaN/0 дали поля'); }
// група: кількість лише в полі C, SIDC той самий
{ const a = A.build({ type: 'tu95', affiliation: 'hostile', count: 6 }), b = A.build({ type: 'tu95', affiliation: 'hostile', count: null });
  if (a.sidc !== b.sidc) fail('кількість змінила SIDC'); if (a.opts.quantity !== '6') fail('кількість не в полі C'); }
// поля SKY не впливають на символ
{ const a = A.sidc('shahed', 'suspect'); A.sky({ source: 'x', ageS: 99999, accuracyKm: 50, estimate: true, stale: true }); if (A.sidc('shahed', 'suspect') !== a) fail('поля SKY змінили SIDC'); }
// стан символу завжди present, зарезервовані позиції нульові
for (const r of A.table()) { if (r.sidc[6] !== '0') fail('статус ≠ 0: ' + r.type); }
// форма рамки відрізняє належність без кольору
{ const m = (a) => new (require('../web/vendor/milsymbol.js').Symbol)(A.sidc('shahed', a), { size: 28, monoColor: 'rgb(240,242,245)' }).asSVG();
  if (m('unknown') === m('hostile') || m('suspect') === m('hostile') || m('unknown') === m('suspect')) fail('чорно-білі рамки не відрізняються'); }
// належність лише за даними
const T = (d, w) => { if (A.affiliationOf(d) !== w) fail('належність ' + JSON.stringify(d) + ' → ' + A.affiliationOf(d) + ', очікувалось ' + w); };
T({}, 'suspect'); T({ indep: 1 }, 'suspect'); T({ indep: 2 }, 'hostile'); T({ idLvl: 'висока' }, 'hostile'); T({ official: true }, 'hostile'); T({ ai: true, indep: 1 }, 'unknown'); T({ ai: true, indep: 2 }, 'hostile');
// таблиця відповідності: кожному типу SKY є запис, відомі типи SKY покриті
for (const t of ['shahed', 'jet', 'molniya', 'cruise', 'ballistic', 'kab', 'geran5', 'banderol', 'rszv', 'fpv', 'fpvf', 'lancet', 'recon', 'tu95', 'tu160', 'tu22', 'mig31'])
  if (!A.MAP[t]) fail('немає відповідності для типу ' + t);
if (bad.length) { console.error(bad.join('\n')); console.error(bad.length + ' порушень'); process.exit(1); }
console.log('APP-6(E): перевірено ' + n + ' символів, порушень немає');
