import {
  Camera,
  type CameraRef,
  GeoJSONSource,
  Images,
  Layer,
  Map,
  type StyleSpecification,
  type ViewStateChangeEvent,
} from '@maplibre/maplibre-react-native';
import type { ExpressionSpecification } from '@maplibre/maplibre-gl-style-spec';
import { memo, type Ref, useEffect, useMemo, useRef, useState } from 'react';
import type { NativeSyntheticEvent } from 'react-native';

import { buildRaionIndex, raionOf, type RaionIndex } from '../lib/geo';
import { C, ESRI, GLYPHS, MAP_FONT } from '../lib/theme';
import type { LonLat, Official, Snapshot } from '../lib/types';
import { LiveLayers } from './LiveLayers';

const SPRITES = {
  't-shahed': require('../../assets/sprites/t-shahed.png'),
  't-jet': require('../../assets/sprites/t-jet.png'),
  't-molniya': require('../../assets/sprites/t-molniya.png'),
  't-cruise': require('../../assets/sprites/t-cruise.png'),
  't-ballistic': require('../../assets/sprites/t-ballistic.png'),
  't-shahed-sh': require('../../assets/sprites/t-shahed-sh.png'),
  't-jet-sh': require('../../assets/sprites/t-jet-sh.png'),
  't-molniya-sh': require('../../assets/sprites/t-molniya-sh.png'),
  't-cruise-sh': require('../../assets/sprites/t-cruise-sh.png'),
  't-ballistic-sh': require('../../assets/sprites/t-ballistic-sh.png'),
};

const STYLE: StyleSpecification = {
  version: 8,
  glyphs: GLYPHS,
  sources: {
    esri: {
      type: 'raster',
      tiles: [ESRI],
      tileSize: 256,
      maxzoom: 19,
      attribution: '© Esri, Maxar, Earthstar Geographics',
    },
  },
  layers: [
    { id: 'bg', type: 'background', paint: { 'background-color': C.bg } },
    { id: 'esri', type: 'raster', source: 'esri', paint: { 'raster-saturation': -0.25, 'raster-brightness-max': 0.82 } },
  ],
};

const EMPTY: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] };

/** Колір заливки за рівнем: 2 → червоний, 1 → жовтий; нічого — прозоро. Лише офіційні тривоги. */
function levelExpr(key: ExpressionSpecification, byLevel: { 1: (string | number)[]; 2: (string | number)[] }, c2: string, c1: string) {
  const arms: (string | number | (string | number)[])[] = [];
  if (byLevel[2].length) arms.push(byLevel[2], c2);
  if (byLevel[1].length) arms.push(byLevel[1], c1);
  if (!arms.length) return { color: '#000000', on: false };
  return { color: ['match', key, ...arms, '#000000'] as unknown as ExpressionSpecification, on: true };
}

function opacityExpr(key: ExpressionSpecification, byLevel: { 1: (string | number)[]; 2: (string | number)[] }, o2: number, o1: number) {
  const arms: (string | number | (string | number)[])[] = [];
  if (byLevel[2].length) arms.push(byLevel[2], o2);
  if (byLevel[1].length) arms.push(byLevel[1], o1);
  if (!arms.length) return 0;
  return ['match', key, ...arms, 0] as unknown as ExpressionSpecification;
}

function raionLevels(idx: RaionIndex[] | null, off: Official | undefined) {
  const out = { 1: [] as number[], 2: [] as number[] };
  if (!idx || !off) return out;
  const lv: Record<number, number> = {};
  const up = (i: number, v: number) => {
    if (i >= 0 && (lv[i] || 0) < v) lv[i] = v;
  };
  const rl = off.raion_levels || {};
  idx.forEach((r) => rl[r.n] && up(r.i, rl[r.n]));
  (off.points || []).forEach(([lo, la, , l]) => up(raionOf(idx, lo, la), l));
  Object.entries(lv).forEach(([i, v]) => out[v === 2 ? 2 : 1].push(Number(i)));
  return out;
}

interface Props {
  server: string;
  snap: Snapshot | null;
  home: LonLat | null;
  selected: string | null;
  onSelect(id: string | null): void;
  onLongPress(p: LonLat): void;
  cameraRef: Ref<CameraRef>;
}

function TacticalMapImpl({ server, snap, home, selected, onSelect, onLongPress, cameraRef }: Props) {
  const [raions, setRaions] = useState<GeoJSON.FeatureCollection | null>(null);
  const [ridx, setRidx] = useState<RaionIndex[] | null>(null);
  const zoomRef = useRef(5.2);

  useEffect(() => {
    let alive = true;
    setRaions(null);
    setRidx(null);
    fetch(server + '/data/raions.geojson')
      .then((r) => r.json())
      .then((fc: GeoJSON.FeatureCollection) => {
        if (!alive) return;
        fc.features.forEach((f, i) => {
          f.properties = { ...(f.properties || {}), i };
        });
        setRidx(buildRaionIndex(fc));
        setRaions(fc);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [server]);

  const off = snap?.official;
  const offKey = JSON.stringify([off?.raion_levels, off?.points, off?.levels]);
  const raPaint = useMemo(() => {
    const by = raionLevels(ridx, off);
    const key: ExpressionSpecification = ['get', 'i'];
    return {
      color: levelExpr(key, by, '#C8102E', '#E8B300').color,
      opacity: opacityExpr(key, by, 0.4, 0.24),
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ridx, offKey]);

  const oblPaint = useMemo(() => {
    const by = { 1: [] as string[], 2: [] as string[] };
    Object.entries(off?.levels || {}).forEach(([n, v]) => by[v === 2 ? 2 : 1].push(n));
    const key: ExpressionSpecification = ['get', 'n'];
    return { color: levelExpr(key, by, '#C8102E', '#E8B300').color, opacity: opacityExpr(key, by, 0.16, 0.14) };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offKey]);

  const zones = useMemo<GeoJSON.FeatureCollection>(
    () => ({
      type: 'FeatureCollection',
      features: (snap?.zones || []).flatMap((z) =>
        z.places.map(([lo, la]) => ({ type: 'Feature' as const, properties: {}, geometry: { type: 'Point' as const, coordinates: [lo, la] } })),
      ),
    }),
    [snap?.zones],
  );

  const homeFc = useMemo<GeoJSON.FeatureCollection>(
    () =>
      home
        ? { type: 'FeatureCollection', features: [{ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: home } }] }
        : EMPTY,
    [home],
  );

  return (
    <Map
      style={{ flex: 1 }}
      mapStyle={STYLE}
      logo={false}
      attribution
      attributionPosition={{ bottom: 8, left: 10 }}
      compass={false}
      scaleBar={false}
      onLongPress={(e) => onLongPress(e.nativeEvent.lngLat as LonLat)}
      onPress={() => onSelect(null)}
      onRegionIsChanging={(e: NativeSyntheticEvent<ViewStateChangeEvent>) => {
        zoomRef.current = e.nativeEvent.zoom;
      }}
      onRegionDidChange={(e: NativeSyntheticEvent<ViewStateChangeEvent>) => {
        zoomRef.current = e.nativeEvent.zoom;
      }}
    >
      <Camera ref={cameraRef} initialViewState={{ center: [33.5, 48.6], zoom: 5.2 }} maxZoom={16} minZoom={3} />
      <Images images={SPRITES} />

      <GeoJSONSource id="obl" data={server + '/data/oblasts.geojson'}>
        <Layer id="obl-fill" type="fill" paint={{ 'fill-color': oblPaint.color, 'fill-opacity': oblPaint.opacity }} />
        <Layer
          id="obl-line"
          type="line"
          paint={{
            'line-color': '#ffffff',
            'line-opacity': 0.8,
            'line-width': ['interpolate', ['linear'], ['zoom'], 4, 0.8, 9, 2],
          }}
        />
      </GeoJSONSource>

      <GeoJSONSource id="ra" data={raions || EMPTY}>
        <Layer id="ra-fill" type="fill" beforeId="obl-line" paint={{ 'fill-color': raPaint.color, 'fill-opacity': raPaint.opacity }} />
        <Layer
          id="ra-line"
          type="line"
          minzoom={5.5}
          beforeId="obl-line"
          paint={{
            'line-color': '#ffffff',
            'line-opacity': ['interpolate', ['linear'], ['zoom'], 5.5, 0.2, 9, 0.5],
            'line-width': ['interpolate', ['linear'], ['zoom'], 6, 0.4, 10, 1.1],
          }}
        />
      </GeoJSONSource>

      <GeoJSONSource id="zones" data={zones}>
        <Layer
          id="zones"
          type="circle"
          paint={{
            'circle-pitch-alignment': 'map',
            'circle-radius': ['interpolate', ['exponential', 2], ['zoom'], 5, 4, 9, 60, 12, 480],
            'circle-color': '#FF7A2E',
            'circle-opacity': 0.16,
            'circle-stroke-color': '#FF7A2E',
            'circle-stroke-width': 1.2,
            'circle-stroke-opacity': 0.7,
          }}
        />
      </GeoJSONSource>

      <GeoJSONSource id="home" data={homeFc}>
        <Layer
          id="home-halo"
          type="circle"
          paint={{ 'circle-radius': 18, 'circle-color': 'rgba(110,168,255,0.18)', 'circle-stroke-color': 'rgba(110,168,255,0.55)', 'circle-stroke-width': 1 }}
        />
        <Layer
          id="home-dot"
          type="circle"
          paint={{ 'circle-radius': 6.5, 'circle-color': C.blue, 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2.5 }}
        />
        <Layer
          id="home-label"
          type="symbol"
          layout={{
            'text-field': 'Дім',
            'text-font': MAP_FONT,
            'text-size': 13,
            'text-offset': [0, 1.6],
            'text-allow-overlap': true,
          }}
          paint={{ 'text-color': '#ffffff', 'text-halo-color': 'rgba(0,0,0,0.85)', 'text-halo-width': 1.6 }}
        />
      </GeoJSONSource>

      <LiveLayers snap={snap} selected={selected} onSelect={onSelect} zoomRef={zoomRef} />
    </Map>
  );
}

export const TacticalMap = memo(TacticalMapImpl);
