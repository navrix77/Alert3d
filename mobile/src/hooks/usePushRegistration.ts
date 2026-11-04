import Constants from 'expo-constants';
import * as Notifications from 'expo-notifications';
import { useEffect, useRef } from 'react';

import { prepareNotifications } from './useHomeAlerts';
import type { LonLat } from '../lib/types';

/**
 * Реєструє телефон на сервері для push-сповіщень (працюють і з заблокованим екраном).
 * Сервер отримує лише Expo-токен і дім, округлений до ~1 км.
 * Потребує EAS projectId (з’являється після `eas init`); без нього лишаються локальні сповіщення.
 */
export function usePushRegistration(server: string, home: LonLat | null) {
  const sent = useRef('');
  useEffect(() => {
    if (!home || !/^https?:\/\//.test(server)) return;
    let cancelled = false;
    (async () => {
      if (!(await prepareNotifications())) return;
      const projectId =
        (Constants.expoConfig?.extra as { eas?: { projectId?: string } } | undefined)?.eas?.projectId ??
        Constants.easConfig?.projectId;
      if (!projectId) return;
      try {
        const { data: token } = await Notifications.getExpoPushTokenAsync({ projectId });
        const lon = Math.round(home[0] * 100) / 100;
        const lat = Math.round(home[1] * 100) / 100;
        const key = `${server}|${token}|${lon},${lat}`;
        if (cancelled || sent.current === key) return;
        const r = await fetch(`${server}/api/push/register`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token, lon, lat }),
        });
        if (r.ok) sent.current = key;
      } catch {
        /* немає мережі — спробуємо при наступній зміні */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [server, home?.[0], home?.[1]]);
}
