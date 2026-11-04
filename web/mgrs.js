/* MGRS (система цілевказання НАТО): широта/довгота WGS-84 → UTM → MGRS (зона, пояс, 100-км квадрат, координати).
 * Методика: «Рекомендації з використання топографічних карт НАТО в ЗСУ», розділ 4.4 (UTM, указівні зони 6°×8°, квадрати 100×100 км).
 * Без полярних зон UPS (north of 84°N / south of 80°S). Прямі формули Крюгера (Karney), похибка менше міліметра в межах зони. */
(function (root, f) { if (typeof module === 'object' && module.exports) module.exports = f(); else root.MGRS = f(); })(typeof self !== 'undefined' ? self : this, function () {
  const A = 6378137, F = 1 / 298.257223563, K0 = 0.9996, N = F / (2 - F), R = A / (1 + N) * (1 + N * N / 4 + N ** 4 / 64 + N ** 6 / 256);
  const al = [N / 2 - 2 * N * N / 3 + 5 * N ** 3 / 16 + 41 * N ** 4 / 180, 13 * N * N / 48 - 3 * N ** 3 / 5 + 557 * N ** 4 / 1440, 61 * N ** 3 / 240 - 103 * N ** 4 / 140, 49561 * N ** 4 / 161280];
  const BANDS = 'CDEFGHJKLMNPQRSTUVWX', COLS = ['ABCDEFGH', 'JKLMNPQR', 'STUVWXYZ'], ROWS = 'ABCDEFGHJKLMNPQRSTUV', rad = Math.PI / 180;
  function zoneOf(lat, lon) {
    let z = Math.floor((lon + 180) / 6) + 1; if (lon === 180) z = 60;
    if (lat >= 56 && lat < 64 && lon >= 3 && lon < 12) z = 32;                       // Норвегія
    if (lat >= 72 && lat < 84) { if (lon >= 0 && lon < 9) z = 31; else if (lon >= 9 && lon < 21) z = 33; else if (lon >= 21 && lon < 33) z = 35; else if (lon >= 33 && lon < 42) z = 37; } // Шпіцберген
    return z;
  }
  function utm(lat, lon) {
    const z = zoneOf(lat, lon), l0 = ((z - 1) * 6 - 180 + 3) * rad, p = lat * rad, dl = lon * rad - l0, e = 2 * Math.sqrt(N) / (1 + N);
    const t = Math.sinh(Math.atanh(Math.sin(p)) - e * Math.atanh(e * Math.sin(p)));
    const xi0 = Math.atan2(t, Math.cos(dl)), et0 = Math.atanh(Math.sin(dl) / Math.sqrt(1 + t * t));
    let xi = xi0, et = et0;
    for (let j = 1; j <= 4; j++) { xi += al[j - 1] * Math.sin(2 * j * xi0) * Math.cosh(2 * j * et0); et += al[j - 1] * Math.cos(2 * j * xi0) * Math.sinh(2 * j * et0); }
    return { zone: z, east: 500000 + K0 * R * et, north: K0 * R * xi + (lat < 0 ? 10000000 : 0) };
  }
  // digits: 1 = 10 км, 2 = 1 км, 3 = 100 м, 4 = 10 м, 5 = 1 м
  function toMGRS(lat, lon, digits) {
    if (!(lat >= -80 && lat <= 84) || !isFinite(lon)) return '';
    digits = Math.max(0, Math.min(5, digits == null ? 3 : digits));
    const u = utm(lat, lon), band = BANDS[Math.min(19, Math.floor((lat + 80) / 8))];
    const col = COLS[(u.zone - 1) % 3][Math.floor(u.east / 100000) - 1], row = ROWS[(Math.floor(u.north / 100000) + (u.zone % 2 === 0 ? 5 : 0)) % 20];
    const q = 10 ** (5 - digits), e = Math.floor((u.east % 100000) / q), n = Math.floor((u.north % 100000) / q);
    const pad = v => String(v).padStart(digits, '0');
    return u.zone + band + col + row + (digits ? ' ' + pad(e) + ' ' + pad(n) : '');
  }
  // скільки цифр відповідає точності (км): ≥10 км → 10 км; ≥1 км → 1 км; інакше 100 м
  const digitsFor = km => (km == null || !isFinite(km)) ? 2 : km >= 10 ? 1 : km >= 1 ? 2 : 3;
  return { toMGRS, utm, zoneOf, digitsFor };
});
