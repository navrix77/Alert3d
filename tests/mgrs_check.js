// MGRS: звірка web/mgrs.js з еталонними векторами (згенеровані пакетом mgrs 2.1.0) та базові перевірки формату
const M = require('../web/mgrs.js'), V = require('./mgrs_vectors.json');
let bad = 0;
for (const [lat, lon, ref] of V) { const got = M.toMGRS(lat, lon, 5).replace(/\s/g, ''); if (got !== ref) { bad++; console.error('MGRS', lat, lon, got, '≠', ref); } }
const k = M.toMGRS(50.4501, 30.5234, 3); if (k !== '36UUA 241 916') { bad++; console.error('Київ', k); }
if (M.toMGRS(50.45, 30.52, 1).split(' ').length !== 3) { bad++; console.error('формат'); }
if (M.toMGRS(89, 30) !== '') { bad++; console.error('полярна зона має давати порожньо'); }
if (M.digitsFor(12) !== 1 || M.digitsFor(3) !== 2 || M.digitsFor(0.4) !== 3 || M.digitsFor(null) !== 2) { bad++; console.error('digitsFor'); }
if (bad) process.exit(1); console.log('MGRS: ' + V.length + ' векторів збігаються');
