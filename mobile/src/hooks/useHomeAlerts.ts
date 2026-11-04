import * as Haptics from 'expo-haptics';
import * as Notifications from 'expo-notifications';
import { useEffect, useRef } from 'react';
import { Platform } from 'react-native';

import { dispPos } from '../lib/display';
import { homeRel } from '../lib/geo';
import { ALERT_KM, TYPE_NAME } from '../lib/theme';
import type { LonLat, Snapshot } from '../lib/types';

// Застосунок відкритий: показуємо лише власні (локальні) сповіщення — серверний push про ту саму ціль не дублюємо.
Notifications.setNotificationHandler({
  handleNotification: async (n) => {
    const remote = (n.request.trigger as { type?: string } | null)?.type === 'push';
    return { shouldShowBanner: !remote, shouldShowList: true, shouldPlaySound: !remote, shouldSetBadge: false };
  },
});

const CHANNEL = 'threats';
let prepared = false;

/** Дозвіл на сповіщення + канал Android високої важливості. Безпечно викликати кілька разів. */
export async function prepareNotifications(): Promise<boolean> {
  try {
    if (Platform.OS === 'android' && !prepared) {
      await Notifications.setNotificationChannelAsync(CHANNEL, {
        name: 'Загрози біля дому',
        importance: Notifications.AndroidImportance.MAX,
        vibrationPattern: [0, 250, 120, 250],
        lightColor: '#C8102E',
      });
    }
    prepared = true;
    const cur = await Notifications.getPermissionsAsync();
    if (cur.granted) return true;
    const req = await Notifications.requestPermissionsAsync();
    return req.granted;
  } catch {
    return false;
  }
}

const REARM_MS = 10 * 60_000;

/**
 * Коли підтверджена ціль (довіра ≥ 50%) маршрутом або курсом наближається до дому ближче ніж на 15 км —
 * вібровідгук і локальне сповіщення. Одне сповіщення на ціль; повторно — лише якщо загроза зникала ≥ 10 хв.
 */
export function useHomeAlerts(snap: Snapshot | null, home: LonLat | null) {
  const fired = useRef(new Map<string, number>()); // id → коли востаннє була загрозою
  const homeKey = home ? home.join(',') : '';

  useEffect(() => {
    fired.current.clear();
  }, [homeKey]);

  useEffect(() => {
    if (!snap || !home) return;
    const now = Date.now();
    const fresh: { title: string; body: string; id: string }[] = [];
    for (const tr of snap.tracks) {
      if (tr.status !== 'active' || tr.conf < 0.5) continue;
      const r = homeRel(tr, dispPos(tr), home);
      if (!r || r.d > 200) continue;
      const threat = r.miss <= ALERT_KM || r.d <= ALERT_KM;
      const prev = fired.current.get(tr.id);
      if (!threat) continue;
      if (prev === undefined || now - prev > REARM_MS) {
        const eta = r.eta != null ? Math.max(1, Math.round(r.eta)) : r.d <= ALERT_KM ? 0 : Math.max(1, Math.round((r.d / tr.speed) * 60));
        fresh.push({
          id: tr.id,
          title: (eta <= 8 ? 'В укриття: ' : 'Увага: ') + TYPE_NAME[tr.type] + (tr.count && tr.count > 1 ? ' ×' + tr.count : ''),
          body:
            (r.d <= ALERT_KM ? 'Ціль за ' + Math.round(r.d) + ' км від дому' : 'Курс/маршрут проходить за ' + Math.round(r.miss) + ' км від дому') +
            ' · ' + Math.round(r.d) + ' км ' + r.from + (eta ? ' · ~' + eta + ' хв' : '') + (tr.next ? ' · → ' + tr.next : ''),
        });
      }
      fired.current.set(tr.id, now);
    }
    if (!fresh.length) return;
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning).catch(() => {});
    setTimeout(() => Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy).catch(() => {}), 320);
    for (const f of fresh) {
      Notifications.scheduleNotificationAsync({
        identifier: 'thr-' + f.id,
        content: { title: f.title, body: f.body, sound: true, data: { id: f.id } },
        trigger: Platform.OS === 'android' ? { channelId: CHANNEL } : null,
      }).catch(() => {});
    }
  }, [snap, home]);
}
