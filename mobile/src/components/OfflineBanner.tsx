import { useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Animated, { FadeInUp, FadeOutUp } from 'react-native-reanimated';

import { clock } from '../hooks/useLiveState';
import { C, R } from '../lib/theme';
import type { ConnState } from '../lib/types';
import { Glass } from './Glass';

/** Банер «немає звʼязку»: скільки секунд без даних і нагадування, що це не відбій. */
export function OfflineBanner({ conn, server }: { conn: ConnState; server: string }) {
  const [, tick] = useState(0);
  useEffect(() => {
    if (conn !== 'offline') return;
    const h = setInterval(() => tick((x) => x + 1), 1000);
    return () => clearInterval(h);
  }, [conn]);
  if (conn !== 'offline') return null;
  const age = clock.recvAt ? Math.round((Date.now() - clock.recvAt) / 1000) : null;
  return (
    <Animated.View entering={FadeInUp.springify()} exiting={FadeOutUp.springify()} style={styles.wrap}>
      <Glass radius={R.md} style={styles.box}>
        <View style={styles.dot} />
        <View style={{ flex: 1 }}>
          <Text style={styles.t}>Немає звʼязку{age != null ? ' · ' + age + ' с' : ''} — це не відбій</Text>
          <Text style={styles.s} numberOfLines={1}>
            Перепідключення до {server}…
          </Text>
        </View>
      </Glass>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginTop: 8 },
  box: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 9, borderColor: 'rgba(255,59,78,0.5)' },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: C.redHot, marginRight: 10 },
  t: { color: C.ink, fontSize: 13.5, fontWeight: '700' },
  s: { color: C.ink3, fontSize: 12, marginTop: 1 },
});
