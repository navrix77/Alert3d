import AsyncStorage from '@react-native-async-storage/async-storage';
import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { DEFAULT_SERVER } from '../lib/theme';
import type { LonLat } from '../lib/types';

const K_SERVER = 'tryvoga.server';
const K_HOME = 'tryvoga.home';

interface Settings {
  ready: boolean;
  server: string;
  home: LonLat | null;
  setServer(url: string): void;
  setHome(p: LonLat | null): void;
}

const Ctx = createContext<Settings | null>(null);

/** Нормалізує адресу сервера: додає http://, прибирає кінцевий слеш. */
export function normalizeServer(raw: string): string {
  let s = raw.trim();
  if (!s) return DEFAULT_SERVER;
  if (!/^https?:\/\//i.test(s)) s = 'http://' + s;
  return s.replace(/\/+$/, '');
}

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [server, setServerS] = useState(DEFAULT_SERVER);
  const [home, setHomeS] = useState<LonLat | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [s, h] = await Promise.all([AsyncStorage.getItem(K_SERVER), AsyncStorage.getItem(K_HOME)]);
        if (s) setServerS(s);
        if (h) {
          const v = JSON.parse(h);
          if (Array.isArray(v) && v.length === 2 && v.every((n) => typeof n === 'number')) setHomeS([v[0], v[1]]);
        }
      } catch {
        /* сховище недоступне — працюємо з типовими значеннями */
      } finally {
        setReady(true);
      }
    })();
  }, []);

  const setServer = useCallback((url: string) => {
    const v = normalizeServer(url);
    setServerS(v);
    AsyncStorage.setItem(K_SERVER, v).catch(() => {});
  }, []);

  const setHome = useCallback((p: LonLat | null) => {
    setHomeS(p);
    (p ? AsyncStorage.setItem(K_HOME, JSON.stringify(p)) : AsyncStorage.removeItem(K_HOME)).catch(() => {});
  }, []);

  const value = useMemo(() => ({ ready, server, home, setServer, setHome }), [ready, server, home, setServer, setHome]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSettings(): Settings {
  const v = useContext(Ctx);
  if (!v) throw new Error('useSettings поза SettingsProvider');
  return v;
}
