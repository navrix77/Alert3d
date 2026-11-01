import { GeoJSONSource, Layer } from '@maplibre/maplibre-react-native';
import type { ExpressionSpecification } from '@maplibre/maplibre-gl-style-spec';
import { type RefObject, useEffect, useRef, useState } from 'react';

import { DISP, stepDisplay } from '../lib/display';
import { dist, fmtTime, metersPerPixel, posAt, xy } from '../lib/geo';
import { MAP_FONT, TYPE_COLOR } from '../lib/theme';
import type { Snapshot } from '../lib/types';
import { serverNow } from '../hooks/useLiveState';

type FC = GeoJSON.FeatureCollection;
const EMPTY: FC = { type: 'FeatureCollection', features: [] };
const fc = (features: GeoJSON.Feature[]): FC => ({ type: 'FeatureCollection', features });
const line = (coordinates: number[][], properties: Record<string, unknown>): GeoJSON.Feature => ({
  type: 'Feature',
  properties,
  geometry: { type: 'LineString', coordinates },
});
const point = (coordinates: number[], properties: Record<string, unknown>): GeoJSON.Feature => ({
  type: 'Feature',
  properties,
  geometry: { type: 'Point', coordinates },
});

interface Frame {
  targets: FC;
  trails: FC;
  preds: FC;
  sel: FC;
  chains: FC;
  lsites: FC;
  ticks: FC;
}
const EMPTY_FRAME: Frame = { targets: EMPTY, trails: EMPTY, preds: EMPTY, sel: EMPTY, chains: EMPTY, lsites: EMPTY, ticks: EMPTY };

const TGS: ExpressionSpecification = ['interpolate', ['linear'], ['zoom'], 4, 0.28, 7, 0.42, 9, 0.58, 12, 0.78];
const FRAME_MS = 33; // ~30 оновлень на секунду в нативний шар — плавно й без перевантаження мосту

interface Props {
  snap: Snapshot | null;
  selected: string | null;
  onSelect(id: string | null): void;
  zoomRef: RefObject<number>;
}

/**
 * Живі шари: спрайти цілей (поворот за курсом), ×N, «→ наступний пункт», пунктирний слід,
 * штриховий ланцюжок пуску (місце пуску → перша фіксація → слід → ціль), прогноз маршруту і позначки +5/+10/+15 хв.
 * Позиції екстраполюються щокадру (requestAnimationFrame) між пушами сервера.
 */
export function LiveLayers({ snap, selected, onSelect, zoomRef }: Props) {
  const [frame, setFrame] = useState<Frame>(EMPTY_FRAME);
  const snapRef = useRef(snap);
  const selRef = useRef(selected);
  snapRef.current = snap;
  selRef.current = selected;

  useEffect(() => {
    let raf = 0;
    let last = Date.now();
    let lastPush = 0;
    let lastChains = 0;
    let lastTicks = 0;
    let chains: FC = EMPTY;
    let lsites: FC = EMPTY;
    let ticks: FC = EMPTY;

    const loop = () => {
      raf = requestAnimationFrame(loop);
      const nowMs = Date.now();
      const dt = Math.min(0.2, (nowMs - last) / 1000);
      last = nowMs;
      const S = snapRef.current;
      if (!S) return;
      const T = serverNow();
      stepDisplay(S, T, dt);
      if (nowMs - lastPush < FRAME_MS) return;
      lastPush = nowMs;
      const sel = selRef.current;

      // ---- цілі, злиття тих, що на екрані лягають одна на одну, в один значок ×N
      const zoom = zoomRef.current ?? 6;
      const active = S.tracks.filter((t) => t.status === 'active').sort((a, b) => (b.conf >= 0.5 ? 1 : 0) - (a.conf >= 0.5 ? 1 : 0));
      type Shown = { f: GeoJSON.Feature; P: [number, number]; type: string; props: Record<string, unknown> };
      const shown: Shown[] = [];
      const trails: GeoJSON.Feature[] = [];
      const preds: GeoJSON.Feature[] = [];
      for (const tr of active) {
        const d = DISP.get(tr.id);
        if (!d) continue;
        const P = xy(d.p);
        const mpp = metersPerPixel(zoom, d.p[1]) / 1000; // км на піксель
        const near = shown.find((g) => g.type === tr.type && dist(g.P, P) / mpp < 34);
        if (near && tr.id !== sel) {
          near.props.count = (near.props.count as number) + (tr.count || 1);
          continue;
        }
        const unk = tr.hd == null;
        const props: Record<string, unknown> = {
          id: tr.id,
          type: tr.type,
          rot: unk ? 0 : d.hd,
          unk,
          weak: tr.conf < 0.5,
          count: tr.count || 1,
          next: tr.next || '',
          sk: sel === tr.id ? 0 : 1,
        };
        shown.push({ f: point(d.p, props), P, type: tr.type, props });
        const c = TYPE_COLOR[tr.type];
        trails.push(line([...tr.trail.slice(-3).map((t) => [t[0], t[1]]), d.p], { c }));
        if (sel === tr.id && tr.route.length) preds.push(line([d.p, ...tr.route], { c }));
      }
      const targets = fc(shown.map((s) => s.f));

      const sd = sel ? DISP.get(sel) : undefined;
      const st = sel ? S.tracks.find((t) => t.id === sel) : undefined;
      const selFc = sd && st ? fc([point(sd.p, { c: TYPE_COLOR[st.type] })]) : EMPTY;

      // ---- ланцюжки пуску (рідше: двічі на секунду)
      if (nowMs - lastChains > 500) {
        lastChains = nowMs;
        const ch: GeoJSON.Feature[] = [];
        const ls = new globalThis.Map<string, GeoJSON.Feature>();
        for (const L of S.launches || []) {
          ls.set(
            L.site,
            point([L.lon, L.lat], { est: false, l: 'ПУСК · ' + L.site.replace(/ \(.*\)/, '') + ' ' + fmtTime(L.t) + (L.count ? ' ×' + L.count : '') }),
          );
        }
        for (const tr of S.tracks) {
          const L = tr.launch;
          if (!L || tr.status === 'closed') continue;
          const isSel = sel === tr.id;
          const d = DISP.get(tr.id);
          if (!d || (L.est && !isSel)) continue;
          const coords: number[][] = [[L.lon, L.lat]];
          if (tr.entry) coords.push([tr.entry[0], tr.entry[1]]);
          tr.trail.forEach((t) => coords.push([t[0], t[1]]));
          coords.push(d.p);
          ch.push(line(coords, { c: L.est ? '#FF8A8A' : '#FF3B3B', o: isSel ? 0.95 : L.est ? 0.3 : 0.42, w: isSel ? 2.6 : 1.4 }));
          if (!ls.has(L.site)) ls.set(L.site, point([L.lon, L.lat], { est: true, l: 'ймовірно · ' + L.site.replace(/ \(.*\)/, '') }));
        }
        chains = fc(ch);
        lsites = fc([...ls.values()]);
      }

      // ---- позначки +5/+10/+15 хв для вибраної цілі
      if (nowMs - lastTicks > 800) {
        lastTicks = nowMs;
        const tk: GeoJSON.Feature[] = [];
        if (st && st.status === 'active') {
          const c = TYPE_COLOR[st.type];
          let lastP = xy(posAt(st, T).p);
          const mpp = metersPerPixel(zoom, st.lat) / 1000;
          for (const m of [5, 10, 15]) {
            const q = posAt(st, T + m * 60).p;
            const Q = xy(q);
            if (dist(Q, lastP) / mpp < 46) continue;
            lastP = Q;
            tk.push(point(q, { c, l: '+' + m + ' хв' }));
          }
        }
        ticks = fc(tk);
      }

      setFrame({ targets, trails: fc(trails), preds: fc(preds), sel: selFc, chains, lsites, ticks });
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [zoomRef]);

  return (
    <>
      <GeoJSONSource id="chains" data={frame.chains}>
        <Layer
          id="chains"
          type="line"
          layout={{ 'line-cap': 'round', 'line-join': 'round' }}
          paint={{ 'line-color': ['get', 'c'], 'line-width': ['get', 'w'], 'line-dasharray': [2, 1.6], 'line-opacity': ['get', 'o'] }}
        />
      </GeoJSONSource>
      <GeoJSONSource id="lsites" data={frame.lsites}>
        <Layer
          id="lsites"
          type="circle"
          paint={{
            'circle-radius': ['case', ['get', 'est'], 5, 7],
            'circle-color': ['case', ['get', 'est'], 'rgba(255,77,77,0.25)', '#FF3B3B'],
            'circle-stroke-color': '#ffffff',
            'circle-stroke-width': ['case', ['get', 'est'], 1.2, 2],
            'circle-pitch-alignment': 'map',
          }}
        />
        <Layer
          id="lsites-t"
          type="symbol"
          layout={{
            'text-field': ['get', 'l'],
            'text-font': MAP_FONT,
            'text-size': 12,
            'text-offset': [0, 1.25],
            'text-anchor': 'top',
            'text-allow-overlap': true,
          }}
          paint={{ 'text-color': '#FFB3B3', 'text-halo-color': '#0B0F17', 'text-halo-width': 2 }}
        />
      </GeoJSONSource>
      <GeoJSONSource id="trails" data={frame.trails}>
        <Layer
          id="trails"
          type="line"
          layout={{ 'line-cap': 'round', 'line-join': 'round' }}
          paint={{ 'line-color': ['get', 'c'], 'line-width': 3, 'line-dasharray': [0.1, 2.2], 'line-opacity': 0.95 }}
        />
      </GeoJSONSource>
      <GeoJSONSource id="preds" data={frame.preds}>
        <Layer
          id="preds"
          type="line"
          layout={{ 'line-cap': 'round' }}
          paint={{ 'line-color': ['get', 'c'], 'line-width': 2, 'line-dasharray': [1.5, 2], 'line-opacity': 0.9 }}
        />
      </GeoJSONSource>
      <GeoJSONSource id="ticks" data={frame.ticks}>
        <Layer
          id="ticks-c"
          type="circle"
          paint={{ 'circle-radius': 4, 'circle-color': ['get', 'c'], 'circle-stroke-color': '#0B0F17', 'circle-stroke-width': 2 }}
        />
        <Layer
          id="ticks-t"
          type="symbol"
          layout={{ 'text-field': ['get', 'l'], 'text-font': MAP_FONT, 'text-size': 12, 'text-offset': [0, -1.1], 'text-allow-overlap': true }}
          paint={{ 'text-color': '#ffffff', 'text-halo-color': 'rgba(0,0,0,0.9)', 'text-halo-width': 1.6 }}
        />
      </GeoJSONSource>
      <GeoJSONSource id="sel" data={frame.sel}>
        <Layer
          id="sel-ring"
          type="circle"
          paint={{
            'circle-pitch-alignment': 'map',
            'circle-radius': 28,
            'circle-color': 'rgba(0,0,0,0)',
            'circle-stroke-color': ['get', 'c'],
            'circle-stroke-width': 2.5,
          }}
        />
      </GeoJSONSource>
      <GeoJSONSource
        id="targets"
        data={frame.targets}
        hitbox={{ top: 22, right: 22, bottom: 22, left: 22 }}
        onPress={(e) => {
          e.stopPropagation();
          const id = e.nativeEvent.features?.[0]?.properties?.id;
          if (typeof id === 'string') onSelect(id);
        }}
      >
        <Layer
          id="tg-sh"
          type="symbol"
          layout={{
            'icon-image': ['concat', 't-', ['get', 'type'], '-sh'],
            'icon-rotate': ['get', 'rot'],
            'icon-rotation-alignment': 'map',
            'icon-pitch-alignment': 'viewport',
            'icon-allow-overlap': true,
            'icon-ignore-placement': true,
            'icon-size': TGS,
          }}
          paint={{ 'icon-opacity': 0.85, 'icon-translate': [10, 16], 'icon-translate-anchor': 'viewport' }}
        />
        <Layer
          id="tg"
          type="symbol"
          layout={{
            'icon-image': ['concat', 't-', ['get', 'type']],
            'icon-rotate': ['get', 'rot'],
            'icon-rotation-alignment': 'map',
            'icon-pitch-alignment': 'viewport',
            'icon-allow-overlap': true,
            'icon-ignore-placement': true,
            'icon-size': TGS,
            'symbol-sort-key': ['get', 'sk'],
          }}
          paint={{ 'icon-opacity': ['case', ['get', 'weak'], 0.6, 1] }}
        />
        <Layer
          id="tg-next"
          type="symbol"
          filter={['!=', ['get', 'next'], '']}
          layout={{
            'text-field': ['concat', '→ ', ['get', 'next']],
            'text-font': MAP_FONT,
            'text-size': 13,
            'text-anchor': 'left',
            'text-offset': [1.9, 0.9],
            'text-allow-overlap': false,
            'symbol-sort-key': ['get', 'sk'],
          }}
          paint={{ 'text-color': '#ffffff', 'text-halo-color': 'rgba(8,10,16,0.92)', 'text-halo-width': 2.2 }}
        />
        <Layer
          id="tg-n"
          type="symbol"
          filter={['>', ['get', 'count'], 1]}
          layout={{
            'text-field': ['concat', '×', ['to-string', ['get', 'count']]],
            'text-font': MAP_FONT,
            'text-size': 13,
            'text-offset': [1.3, -1.2],
            'text-allow-overlap': true,
          }}
          paint={{ 'text-color': '#ffffff', 'text-halo-color': 'rgba(8,10,16,0.95)', 'text-halo-width': 2.4 }}
        />
        <Layer
          id="tg-unk"
          type="symbol"
          filter={['==', ['get', 'unk'], true]}
          layout={{ 'text-field': 'курс ?', 'text-font': MAP_FONT, 'text-size': 11, 'text-offset': [0, 2.2], 'text-allow-overlap': true }}
          paint={{ 'text-color': '#F5B83D', 'text-halo-color': 'rgba(8,10,16,0.95)', 'text-halo-width': 2 }}
        />
      </GeoJSONSource>
    </>
  );
}
