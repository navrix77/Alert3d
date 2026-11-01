import BottomSheet, { type BottomSheetBackgroundProps, BottomSheetScrollView } from '@gorhom/bottom-sheet';
import { forwardRef, useEffect, useMemo, useState } from 'react';
import { Image, Linking, Pressable, StyleSheet, Text, View } from 'react-native';

import { dispPos } from '../lib/display';
import { courseWord, fmtTime, homeRel, routeEtas } from '../lib/geo';
import { C, R, TYPE_COLOR, TYPE_NAME } from '../lib/theme';
import type { LonLat, Snapshot, Track } from '../lib/types';
import { serverNow } from '../hooks/useLiveState';
import { Glass } from './Glass';
import { typeIcon } from './HomePanel';

function SheetGlass({ style }: BottomSheetBackgroundProps) {
  return <Glass radius={R.xl} style={[style, { shadowOpacity: 0.5 }]} intensity={60} />;
}

const plural = (n: number, one: string, few: string, many: string) => {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
};

const open = (url: string) => Linking.openURL(url).catch(() => {});

function postFor(tr: Track, snap: Snapshot, src: string): string | undefined {
  const slug = (snap.sources[src]?.url || '').split('/').filter(Boolean).pop();
  if (!slug) return undefined;
  return tr.links.filter((l) => l.includes('/' + slug + '/')).pop();
}

interface Props {
  snap: Snapshot | null;
  home: LonLat | null;
  selected: string | null;
  follow: boolean;
  onClose(): void;
  onToggleFollow(): void;
}

/** Картка цілі (нижній аркуш): тип, курс, відстань/ETA до дому, ETA по маршруту, «Звідки запущено», підтвердження. */
export const TargetSheet = forwardRef<BottomSheet, Props>(function TargetSheet({ snap, home, selected, follow, onClose, onToggleFollow }, ref) {
  const snapPoints = useMemo(() => ['42%', '86%'], []);
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!selected) return;
    const h = setInterval(() => setTick((x) => x + 1), 500);
    return () => clearInterval(h);
  }, [selected]);

  const tr = selected && snap ? snap.tracks.find((t) => t.id === selected) : undefined;

  return (
    <BottomSheet
      ref={ref}
      index={-1}
      snapPoints={snapPoints}
      enablePanDownToClose
      enableDynamicSizing={false}
      onClose={onClose}
      backgroundComponent={SheetGlass}
      handleIndicatorStyle={{ backgroundColor: 'rgba(255,255,255,0.4)', width: 42 }}
    >
      <BottomSheetScrollView contentContainerStyle={styles.body}>
        {tr && snap ? <Card tr={tr} snap={snap} home={home} follow={follow} onToggleFollow={onToggleFollow} /> : <Text style={styles.muted}>Ціль більше не відстежується.</Text>}
      </BottomSheetScrollView>
    </BottomSheet>
  );
});

function Card({ tr, snap, home, follow, onToggleFollow }: { tr: Track; snap: Snapshot; home: LonLat | null; follow: boolean; onToggleFollow(): void }) {
  const p = dispPos(tr);
  const r = homeRel(tr, p, home);
  const color = TYPE_COLOR[tr.type];
  const etas = routeEtas(tr, p);
  const ago = Math.round((serverNow() - tr.first) / 60);
  const n = tr.srcs.length;
  const L = tr.launch;
  const course =
    tr.status !== 'active'
      ? tr.status === 'lost'
        ? 'Втрачено'
        : 'Більше не фіксується'
      : tr.next
        ? 'Курс → ' + tr.next
        : tr.hd != null
          ? 'Курс на ' + courseWord(tr.hd)
          : 'Курс уточнюється';
  const why = tr.pred === 'learned' ? 'вивчено з історії' + (tr.pred_p ? ' (' + Math.round(tr.pred_p * 100) + '%)' : '') : tr.pred === 'channels' ? 'за каналами' : '';
  const lastLink = tr.links[tr.links.length - 1];

  return (
    <View>
      <View style={styles.head}>
        <View style={[styles.iconWrap, { borderColor: color + '88', backgroundColor: color + '22' }]}>
          <Image source={typeIcon(tr.type)} style={[styles.icon, tr.hd != null && { transform: [{ rotate: tr.hd + 'deg' }] }]} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.title}>
            {TYPE_NAME[tr.type]}
            {tr.count && tr.count > 1 ? ' ×' + tr.count : ''}
          </Text>
          <Text style={[styles.course, { color }]}>{course}</Text>
        </View>
        <Pressable onPress={onToggleFollow} style={[styles.pill, follow && { backgroundColor: 'rgba(110,168,255,0.28)', borderColor: C.blue }]}>
          <Text style={styles.pillTxt}>{follow ? 'Стежу' : 'Стежити'}</Text>
        </Pressable>
      </View>

      <View style={styles.stats}>
        <Stat k="До дому" v={!home ? 'вкажіть дім' : r ? Math.round(r.d) + ' км' : '—'} s={r?.from} />
        <Stat k="Прибуття" v={!home ? '—' : r?.eta != null ? '~' + Math.max(1, Math.round(r.eta)) + ' хв' : 'не в бік дому'} hot={r?.eta != null && r.eta <= 8} />
        <Stat k="Швидкість" v={tr.speed + ' км/год'} />
        <Stat k="Довіра" v={Math.round(tr.conf * 100) + '%'} s={tr.conf < 0.5 ? 'непідтверджено' : undefined} />
      </View>

      {etas.length > 0 && (
        <Section title={'Прогноз маршруту' + (why ? ' · ' + why : '')}>
          {etas.map((e, i) => (
            <View key={i} style={styles.routeRow}>
              <View style={[styles.dot, { backgroundColor: color }]} />
              <Text style={styles.routeName}>{e.name}</Text>
              <Text style={styles.routeEta}>~{e.min} хв</Text>
            </View>
          ))}
          {home && r?.eta != null && (
            <View style={styles.routeRow}>
              <View style={[styles.dot, { backgroundColor: C.blue }]} />
              <Text style={[styles.routeName, { color: C.blue }]}>ваш дім</Text>
              <Text style={styles.routeEta}>~{Math.max(1, Math.round(r.eta))} хв</Text>
            </View>
          )}
          {tr.pos_est && (
            <Text style={styles.note}>
              Точне місце не названо — позицію оцінено {tr.pred === 'learned-origin' ? 'за типовими маршрутами' : 'по пункту призначення'}.
            </Text>
          )}
        </Section>
      )}

      <Section title="Звідки запущено">
        {L ? (
          <View>
            <Text style={styles.line}>
              {L.est ? <Text style={styles.est}>ймовірно </Text> : null}
              <Text style={styles.bold}>{L.site}</Text>
              {L.carrier ? ' · ' + L.carrier : ''}
              {L.t ? ' · пуск ' + fmtTime(L.t) : ''}
            </Text>
            <Text style={styles.note}>
              {L.est
                ? 'Оцінка за курсом' + (L.p >= 0.4 ? ' і статистикою' : '')
                : (L.srcs || []).map((s) => snap.sources[s]?.name || s).join(', ') || 'за повідомленнями каналів'}
            </Text>
            {!L.est && L.link ? <LinkBtn label="Пост про пуск ↗" url={L.link} /> : null}
          </View>
        ) : (
          <Text style={styles.line}>{tr.from ? 'з боку ' + tr.from : 'Канали не вказали'}</Text>
        )}
        {tr.entry ? (
          <Text style={styles.note}>
            Перша фіксація: {tr.entry[2]} · {fmtTime(tr.entry[3])} · {ago} хв тому
          </Text>
        ) : null}
      </Section>

      <Section title={'Підтвердження: ' + n + ' ' + plural(n, 'канал', 'канали', 'каналів') + (n >= 2 ? ' · незалежно' : ' · лише одне джерело')}>
        <View style={styles.bar}>
          {[0, 1, 2, 3].map((i) => (
            <View key={i} style={[styles.barSeg, i < n && { backgroundColor: n >= 2 ? C.green : C.amber }]} />
          ))}
        </View>
        {tr.srcs.map((s) => {
          const link = postFor(tr, snap, s);
          return (
            <View key={s} style={styles.srcRow}>
              <Text style={styles.srcName}>{snap.sources[s]?.name || s}</Text>
              {link ? (
                <Pressable onPress={() => open(link)} hitSlop={8}>
                  <Text style={styles.link}>пост ↗</Text>
                </Pressable>
              ) : null}
            </View>
          );
        })}
        {lastLink ? <LinkBtn label="Останній пост ↗" url={lastLink} /> : null}
      </Section>
    </View>
  );
}

function Stat({ k, v, s, hot }: { k: string; v: string; s?: string; hot?: boolean }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statK}>{k}</Text>
      <Text style={[styles.statV, hot && { color: C.redHot }]} numberOfLines={1} adjustsFontSizeToFit>
        {v}
      </Text>
      {s ? <Text style={styles.statS} numberOfLines={1}>{s}</Text> : null}
    </View>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text style={styles.h4}>{title}</Text>
      {children}
    </View>
  );
}

function LinkBtn({ label, url }: { label: string; url: string }) {
  return (
    <Pressable onPress={() => open(url)} style={({ pressed }) => [styles.linkBtn, pressed && { opacity: 0.6 }]}>
      <Text style={styles.linkBtnTxt}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  body: { paddingHorizontal: 18, paddingBottom: 48 },
  muted: { color: C.ink3, fontSize: 14, textAlign: 'center', marginTop: 24 },
  head: { flexDirection: 'row', alignItems: 'center', gap: 12, marginTop: 4 },
  iconWrap: { width: 52, height: 52, borderRadius: 16, borderWidth: 1, alignItems: 'center', justifyContent: 'center' },
  icon: { width: 40, height: 40 },
  title: { color: C.ink, fontSize: 21, fontWeight: '700', letterSpacing: -0.4 },
  course: { fontSize: 14, fontWeight: '600', marginTop: 2 },
  pill: { paddingHorizontal: 12, paddingVertical: 7, borderRadius: 999, borderWidth: 1, borderColor: C.hairStrong, backgroundColor: 'rgba(255,255,255,0.06)' },
  pillTxt: { color: C.ink, fontSize: 13, fontWeight: '600' },
  stats: { flexDirection: 'row', flexWrap: 'wrap', marginTop: 16, gap: 8 },
  stat: { width: '48.5%', padding: 12, borderRadius: R.md, backgroundColor: 'rgba(255,255,255,0.06)', borderWidth: StyleSheet.hairlineWidth, borderColor: C.hair },
  statK: { color: C.ink3, fontSize: 12, textTransform: 'uppercase', letterSpacing: 0.6 },
  statV: { color: C.ink, fontSize: 19, fontWeight: '700', marginTop: 3, fontVariant: ['tabular-nums'] },
  statS: { color: C.ink2, fontSize: 12, marginTop: 1 },
  section: { marginTop: 18 },
  h4: { color: C.ink2, fontSize: 13, fontWeight: '600', marginBottom: 8 },
  routeRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 5 },
  dot: { width: 8, height: 8, borderRadius: 4, marginRight: 10 },
  routeName: { color: C.ink, fontSize: 15, flex: 1 },
  routeEta: { color: C.ink, fontSize: 15, fontWeight: '700', fontVariant: ['tabular-nums'] },
  line: { color: C.ink, fontSize: 15, lineHeight: 21 },
  bold: { fontWeight: '700' },
  est: { color: '#FF8A8A', fontStyle: 'italic' },
  note: { color: C.ink3, fontSize: 12.5, marginTop: 4, lineHeight: 17 },
  bar: { flexDirection: 'row', gap: 4, marginBottom: 8 },
  barSeg: { flex: 1, height: 4, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.12)' },
  srcRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 6, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: C.hair },
  srcName: { color: C.ink, fontSize: 14.5, flex: 1 },
  link: { color: C.blue, fontSize: 14, fontWeight: '600' },
  linkBtn: { marginTop: 10, alignSelf: 'flex-start', paddingHorizontal: 14, paddingVertical: 8, borderRadius: 999, backgroundColor: 'rgba(110,168,255,0.16)' },
  linkBtnTxt: { color: C.blue, fontSize: 14, fontWeight: '600' },
});
