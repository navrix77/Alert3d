/**
 * Відображувані позиції цілей. Кадровий цикл щокадру рахує posAt() (екстраполяція між пушами сервера)
 * і плавно «доганяє» її експоненційним згладжуванням — як DISP у web/app.js.
 * Панелі (дім, картка цілі) читають ці позиції без зайвих ререндерів.
 */
import { homeRel, type HomeRel, posAt } from './geo';
import type { LonLat, Snapshot, Track } from './types';

export interface Disp {
  p: LonLat;
  hd: number;
}

export const DISP = new Map<string, Disp>();

export function stepDisplay(snap: Snapshot, serverT: number, dt: number): void {
  const seen = new Set<string>();
  for (const tr of snap.tracks) {
    seen.add(tr.id);
    const { p, hd } = posAt(tr, serverT);
    let d = DISP.get(tr.id);
    if (!d || Math.abs(d.p[0] - p[0]) + Math.abs(d.p[1] - p[1]) > 1.2) {
      DISP.set(tr.id, { p: [p[0], p[1]], hd: hd ?? 0 });
      continue;
    }
    const k = Math.min(1, dt * 3);
    d.p = [d.p[0] + (p[0] - d.p[0]) * k, d.p[1] + (p[1] - d.p[1]) * k];
    if (hd != null) {
      let a = hd - d.hd;
      while (a > 180) a -= 360;
      while (a < -180) a += 360;
      d.hd = (d.hd + a * Math.min(1, dt * 2.5) + 360) % 360;
    }
  }
  for (const id of DISP.keys()) if (!seen.has(id)) DISP.delete(id);
}

export const dispPos = (tr: Track): LonLat => DISP.get(tr.id)?.p ?? [tr.lon, tr.lat];

export interface Near {
  tr: Track;
  r: HomeRel;
}

/** Підтверджені активні цілі в радіусі 120 км від дому, загрози (rel) — першими за ETA. */
export function nearHome(snap: Snapshot | null, home: LonLat | null): { near: Near[]; threats: Near[] } {
  if (!snap || !home) return { near: [], threats: [] };
  const near: Near[] = [];
  for (const tr of snap.tracks) {
    if (tr.status !== 'active' || tr.conf < 0.5) continue;
    const r = homeRel(tr, dispPos(tr), home);
    if (r && r.d < 120) near.push({ tr, r });
  }
  near.sort((a, b) => (a.r.eta ?? 999) - (b.r.eta ?? 999) || a.r.d - b.r.d);
  return { near, threats: near.filter((x) => x.r.rel) };
}
