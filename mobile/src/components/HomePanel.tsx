import { Image, Pressable, StyleSheet, Text, View } from 'react-native';
import Animated, { FadeInUp, LinearTransition } from 'react-native-reanimated';
import { useEffect, useState } from 'react';

import { nearHome, type Near } from '../lib/display';
import { C, R, SPRING, TYPE_NAME, TYPES } from '../lib/theme';
import type { ConnState, LonLat, Snapshot, TargetType } from '../lib/types';
import { Glass, SpringButton } from './Glass';
import { StatusOrb, type OrbTone } from './StatusOrb';

const ICON: Record<TargetType, number> = {
  shahed: require('../../assets/sprites/t-shahed.png'),
  jet: require('../../assets/sprites/t-jet.png'),
  molniya: require('../../assets/sprites/t-molniya.png'),
  cruise: require('../../assets/sprites/t-cruise.png'),
  ballistic: require('../../assets/sprites/t-ballistic.png'),
};
export const typeIcon = (t: TargetType) => ICON[t];

interface Props {
  snap: Snapshot | null;
  conn: ConnState;
  home: LonLat | null;
  onOpen(id: string): void;
  onSettings(): void;
}

export interface HomeSummary {
  tone: OrbTone;
  word: string;
  sub: string;
  list: Near[];
}

function summarize(snap: Snapshot | null, conn: ConnState, home: LonLat | null): HomeSummary {
  if (conn === 'offline' || !snap) {
    return { tone: 'unknown', word: 'Невідомо', sub: snap ? 'Немає звʼязку з сервером. Це не відбій.' : 'Підключення до сервера…', list: [] };
  }
  if (!home) {
    return { tone: 'calm', word: 'Мій дім', sub: 'Довго натисніть на карту, щоб позначити дім — тут зʼявиться особистий таймер.', list: [] };
  }
  const { near, threats } = nearHome(snap, home);
  const first = threats[0];
  if (!first) {
    const n = near[0];
    return {
      tone: 'calm',
      word: 'Спокійно',
      sub: 'Підтверджених цілей у бік дому немає. Найближча: ' + (n ? Math.round(n.r.d) + ' км ' + n.r.from : 'далі 120 км') + '.',
      list: near.slice(0, 2),
    };
  }
  const eta = first.r.eta != null ? Math.max(1, Math.round(first.r.eta)) : null;
  const danger = eta != null && eta <= 8;
  return {
    tone: danger ? 'danger' : 'watch',
    word: danger ? 'В укриття' : 'Увага',
    sub:
      TYPE_NAME[first.tr.type] +
      (first.tr.count && first.tr.count > 1 ? ' ×' + first.tr.count : '') +
      ' · ' +
      (first.r.rel === 'route' ? 'маршрут біля дому' : 'курс у ваш бік') +
      (eta != null ? ' · ~' + eta + ' хв' : ''),
    list: threats.slice(0, 3),
  };
}

/** Верхня скляна панель «Мій дім»: статус-сфера, найближча загроза й хвилини до неї, лічильники цілей. */
export function HomePanel({ snap, conn, home, onOpen, onSettings }: Props) {
  const [sum, setSum] = useState<HomeSummary>(() => summarize(snap, conn, home));
  useEffect(() => {
    setSum(summarize(snap, conn, home));
    const h = setInterval(() => setSum(summarize(snap, conn, home)), 700);
    return () => clearInterval(h);
  }, [snap, conn, home]);

  const by: Partial<Record<TargetType, number>> = {};
  (snap?.tracks || []).filter((t) => t.status === 'active').forEach((t) => (by[t.type] = (by[t.type] || 0) + (t.count || 1)));
  const counters = TYPES.filter((t) => by[t]);
  const ch = snap?.health?.channels;

  return (
    <Animated.View entering={FadeInUp.springify().damping(SPRING.damping).stiffness(SPRING.stiffness)} layout={LinearTransition.springify()}>
      <Glass radius={R.xl} style={styles.panel}>
        <View style={styles.row}>
          <StatusOrb tone={sum.tone} size={46} />
          <View style={{ flex: 1, marginLeft: 10 }}>
            <Text style={[styles.word, sum.tone === 'danger' && { color: C.redHot }]}>{sum.word}</Text>
            <Text style={styles.sub} numberOfLines={2}>
              {sum.sub}
            </Text>
          </View>
          <SpringButton onPress={onSettings} hitSlop={10} style={styles.gear} accessibilityLabel="Налаштування">
            <Text style={styles.gearTxt}>⚙︎</Text>
          </SpringButton>
        </View>

        {sum.list.length > 0 && (
          <View style={styles.list}>
            {sum.list.map(({ tr, r }) => {
              const eta = r.eta != null ? Math.max(1, Math.round(r.eta)) : null;
              return (
                <Pressable key={tr.id} onPress={() => onOpen(tr.id)} style={({ pressed }) => [styles.item, pressed && { opacity: 0.6 }]}>
                  <Image source={ICON[tr.type]} style={[styles.icon, tr.hd != null && { transform: [{ rotate: tr.hd + 'deg' }] }]} />
                  <Text style={styles.itemTxt} numberOfLines={1}>
                    {TYPE_NAME[tr.type]}
                    {tr.count && tr.count > 1 ? ' ×' + tr.count : ''} · {Math.round(r.d)} км {r.from}
                  </Text>
                  <Text style={[styles.eta, r.rel && eta != null && eta <= 8 && { color: C.redHot }]}>{r.rel && eta != null ? '~' + eta + ' хв' : '—'}</Text>
                </Pressable>
              );
            })}
          </View>
        )}

        <View style={styles.foot}>
          <View style={styles.counters}>
            {counters.length ? (
              counters.map((t) => (
                <View key={t} style={styles.chip}>
                  <Image source={ICON[t]} style={styles.chipIcon} />
                  <Text style={styles.chipTxt}>{by[t]}</Text>
                </View>
              ))
            ) : (
              <Text style={styles.footTxt}>{snap ? 'Цілей не видно' : ''}</Text>
            )}
          </View>
          {ch ? (
            <Text style={styles.footTxt}>
              наживо {ch.live}/{ch.channels}
            </Text>
          ) : null}
        </View>
      </Glass>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  panel: { paddingHorizontal: 14, paddingTop: 12, paddingBottom: 10 },
  row: { flexDirection: 'row', alignItems: 'center' },
  word: { color: C.ink, fontSize: 20, fontWeight: '700', letterSpacing: -0.4 },
  sub: { color: C.ink2, fontSize: 13, marginTop: 2, lineHeight: 17 },
  gear: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(255,255,255,0.08)' },
  gearTxt: { color: C.ink, fontSize: 18 },
  list: { marginTop: 10, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: C.hair, paddingTop: 6 },
  item: { flexDirection: 'row', alignItems: 'center', paddingVertical: 6 },
  icon: { width: 22, height: 22, marginRight: 8 },
  itemTxt: { color: C.ink, fontSize: 14, flex: 1 },
  eta: { color: C.ink, fontSize: 15, fontWeight: '700', fontVariant: ['tabular-nums'], marginLeft: 8 },
  foot: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 8 },
  counters: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, flex: 1 },
  chip: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 8, paddingVertical: 3, borderRadius: R.sm, backgroundColor: 'rgba(255,255,255,0.07)' },
  chipIcon: { width: 16, height: 16, marginRight: 4 },
  chipTxt: { color: C.ink, fontSize: 13, fontWeight: '700', fontVariant: ['tabular-nums'] },
  footTxt: { color: C.ink3, fontSize: 12 },
});
