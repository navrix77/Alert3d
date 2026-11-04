/**
 * Геометрія — дзеркало web/app.js: локальна рівнопроміжна проєкція навколо (31.5°E, 49°N) у кілометрах,
 * екстраполяція позиції цілі вздовж маршруту (posAt) і відношення цілі до дому (homeRel).
 */
import type { LonLat, Track } from './types';

const D2R = Math.PI / 180;
const KX = 111.32 * Math.cos(49 * D2R);
const KY = 110.57;

export type XY = [number, number];

export const xy = ([lon, lat]: LonLat | number[]): XY => [(lon - 31.5) * KX, (lat - 49) * KY];
export const ll = ([x, y]: XY): LonLat => [x / KX + 31.5, 49 + y / KY];
export const dist = (a: XY, b: XY): number => Math.hypot(a[0] - b[0], a[1] - b[1]);
export const brg = (a: XY, b: XY): number => ((Math.atan2(b[0] - a[0], b[1] - a[1]) / D2R) + 360) % 360;
export const angd = (a: number, b: number): number => {
  const d = Math.abs(a - b) % 360;
  return d > 180 ? 360 - d : d;
};

export const FROM = [
  'з півночі', 'з північного сходу', 'зі сходу', 'з південного сходу',
  'з півдня', 'з південного заходу', 'з заходу', 'з північного заходу',
];

const COURSE = ['північ', 'північний схід', 'схід', 'південний схід', 'південь', 'південний захід', 'захід', 'північний захід'];
export const courseWord = (hd: number) => COURSE[Math.round(hd / 45) % 8];

export function fmtTime(t: number): string {
  const d = new Date(t * 1000);
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(d.getHours())}:${p(d.getMinutes())}`;
}
export function fmtTimeS(t: number): string {
  const d = new Date(t * 1000);
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

export interface PosHd {
  p: LonLat;
  hd: number | null;
}

/** Позиція цілі в момент serverT: рух зі швидкістю speed від (lon,lat) знімка вздовж route або за курсом. */
export function posAt(tr: Track, serverT: number): PosHd {
  if (tr.status !== 'active') return { p: [tr.lon, tr.lat], hd: tr.hd };
  const km = (tr.speed * Math.max(0, serverT - tr.ts)) / 3600;
  const pts: XY[] = [xy([tr.lon, tr.lat]), ...tr.route.map(xy)];
  if (pts.length === 1) {
    if (tr.hd == null) return { p: [tr.lon, tr.lat], hd: tr.hd };
    const r = tr.hd * D2R;
    return { p: ll([pts[0][0] + Math.sin(r) * km, pts[0][1] + Math.cos(r) * km]), hd: tr.hd };
  }
  let acc = 0;
  for (let i = 1; i < pts.length; i++) {
    const d = dist(pts[i - 1], pts[i]);
    if (acc + d >= km) {
      const f = (km - acc) / (d || 1);
      const q: XY = [pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * f, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * f];
      return { p: ll(q), hd: brg(pts[i - 1], pts[i]) };
    }
    acc += d;
  }
  return { p: ll(pts[pts.length - 1]), hd: tr.hd };
}

export interface HomeRel {
  /** відстань від цілі до дому, км */
  d: number;
  /** 'route' — маршрут проходить біля дому; 'heading' — курс у бік дому */
  rel: 'route' | 'heading' | null;
  /** хвилин до дому (якщо rel) */
  eta: number | null;
  /** найменша відстань, на яку маршрут/курс наблизиться до дому, км */
  miss: number;
  from: string;
}

function segClosest(H: XY, a: XY, b: XY): { d: number; t: number; L: number } {
  const vx = b[0] - a[0];
  const vy = b[1] - a[1];
  const L2 = vx * vx + vy * vy;
  let t = L2 ? ((H[0] - a[0]) * vx + (H[1] - a[1]) * vy) / L2 : 0;
  t = Math.max(0, Math.min(1, t));
  const q: XY = [a[0] + vx * t, a[1] + vy * t];
  return { d: dist(H, q), t, L: Math.sqrt(L2) };
}

/** Відношення цілі (у поточній позиції p) до дому — як homeRel() у web/app.js, плюс miss для сповіщень. */
export function homeRel(tr: Track, p: LonLat, home: LonLat | null): HomeRel | null {
  if (!home) return null;
  const H = xy(home);
  const P = xy(p);
  const d = dist(H, P);
  let rel: HomeRel['rel'] = null;
  let eta: number | null = null;
  const path: XY[] = [P, ...tr.route.map(xy)];
  let acc = 0;
  let best = { d: 1e9, c: 0 };
  for (let i = 1; i < path.length; i++) {
    const s = segClosest(H, path[i - 1], path[i]);
    if (s.d < best.d) best = { d: s.d, c: acc + s.L * s.t };
    acc += s.L;
  }
  // курс без маршруту (або після кінця маршруту): промінь на 250 км уперед
  let miss = best.d;
  if (tr.hd != null) {
    const start = path[path.length - 1];
    const r = tr.hd * D2R;
    const end: XY = [start[0] + Math.sin(r) * 250, start[1] + Math.cos(r) * 250];
    if (path.length === 1) miss = Math.min(miss, segClosest(H, start, end).d);
  }
  if (path.length === 1) miss = Math.min(miss, d);
  if (best.d < 8) {
    rel = 'route';
    eta = (best.c / tr.speed) * 60;
  } else if (tr.hd != null && angd(tr.hd, brg(P, H)) < 20) {
    rel = 'heading';
    eta = (d / tr.speed) * 60;
  }
  return { d, rel, eta, miss, from: FROM[Math.round(brg(H, P) / 45) % 8] };
}

/** ETA до кожного пункту маршруту (хвилини) від поточної позиції. */
export function routeEtas(tr: Track, p: LonLat): { name: string; min: number }[] {
  if (!tr.route_names?.length || !tr.route?.length) return [];
  let acc = 0;
  let prev = xy(p);
  return tr.route.slice(0, tr.route_names.length).map((q, i) => {
    const Q = xy(q);
    acc += dist(prev, Q);
    prev = Q;
    return { name: tr.route_names[i], min: Math.max(1, Math.round((acc / tr.speed) * 60)) };
  });
}

/* ---------- точка в полігоні (для офіційних точок-громад → район) ---------- */
type Ring = number[][];
function inRing(r: Ring, x: number, y: number): boolean {
  let c = false;
  for (let i = 0, j = r.length - 1; i < r.length; j = i++) {
    const xi = r[i][0], yi = r[i][1], xj = r[j][0], yj = r[j][1];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi || 1e-12) + xi) c = !c;
  }
  return c;
}

export interface RaionIndex {
  i: number;
  n: string;
  polys: Ring[][];
  bb: [number, number, number, number];
}

export function buildRaionIndex(fc: GeoJSON.FeatureCollection): RaionIndex[] {
  return fc.features.map((f, i) => {
    const g = f.geometry as GeoJSON.Polygon | GeoJSON.MultiPolygon;
    const polys = (g.type === 'Polygon' ? [g.coordinates] : g.coordinates) as Ring[][];
    const bb: [number, number, number, number] = [180, 90, -180, -90];
    polys.forEach((pl) =>
      pl[0].forEach(([x, y]) => {
        bb[0] = Math.min(bb[0], x); bb[1] = Math.min(bb[1], y);
        bb[2] = Math.max(bb[2], x); bb[3] = Math.max(bb[3], y);
      }),
    );
    return { i, n: String((f.properties as { n?: string } | null)?.n ?? ''), polys, bb };
  });
}

export function raionOf(idx: RaionIndex[], lon: number, lat: number): number {
  for (const r of idx) {
    if (lon < r.bb[0] || lon > r.bb[2] || lat < r.bb[1] || lat > r.bb[3]) continue;
    for (const pl of r.polys) if (inRing(pl[0], lon, lat)) return r.i;
  }
  return -1;
}

/** Метрів на піксель на заданому зумі (Web Mercator, 512-px тайли MapLibre). */
export const metersPerPixel = (zoom: number, lat: number) => (40075016.686 * Math.cos(lat * D2R)) / (512 * 2 ** zoom);
