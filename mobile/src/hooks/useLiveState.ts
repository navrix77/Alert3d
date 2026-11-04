import { useEffect, useRef, useState } from 'react';
import { AppState } from 'react-native';

import type { ConnState, Snapshot } from '../lib/types';

/** Різниця «час сервера − час телефона», с. Спільна для кадрового циклу. */
export const clock = { offset: 0, recvAt: 0 };
export const serverNow = () => Date.now() / 1000 + clock.offset;

const STALE_MS = 20_000;

/**
 * Живий стан: WebSocket /ws (сервер штовхає знімок кожні ~2 с) + початковий GET /api/state.
 * Автоперепідключення з експоненційною паузою 1 → 15 с (з джитером), ping кожні 20 с,
 * миттєве перепідключення при поверненні застосунку на передній план.
 */
export function useLiveState(server: string, enabled: boolean) {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [conn, setConn] = useState<ConnState>('connecting');
  const [lastError, setLastError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    let backoff = 1000;
    let retry: ReturnType<typeof setTimeout> | null = null;

    const onSnap = (s: Snapshot) => {
      if (!alive || !s || !Array.isArray(s.tracks)) return;
      clock.recvAt = Date.now();
      clock.offset = s.now - Date.now() / 1000;
      setSnap(s);
      setConn('live');
      setLastError(null);
    };

    const wsUrl = server.replace(/^http/i, 'ws') + '/ws';

    const schedule = () => {
      if (!alive || retry) return;
      const wait = backoff * (0.8 + Math.random() * 0.4);
      backoff = Math.min(backoff * 2, 15_000);
      retry = setTimeout(() => {
        retry = null;
        connect();
      }, wait);
    };

    const connect = () => {
      if (!alive) return;
      try {
        wsRef.current?.close();
      } catch {
        /* ignore */
      }
      let ws: WebSocket;
      try {
        ws = new WebSocket(wsUrl);
      } catch (e) {
        setLastError(String(e));
        setConn('offline');
        schedule();
        return;
      }
      wsRef.current = ws;
      ws.onopen = () => {
        backoff = 1000;
      };
      ws.onmessage = (e) => {
        backoff = 1000;
        try {
          onSnap(JSON.parse(String(e.data)));
        } catch {
          /* битий кадр — чекаємо наступний */
        }
      };
      ws.onerror = (e) => {
        setLastError((e as unknown as { message?: string }).message || 'помилка зʼєднання');
      };
      ws.onclose = () => {
        if (wsRef.current === ws) wsRef.current = null;
        if (!alive) return;
        if (Date.now() - clock.recvAt > STALE_MS) setConn('offline');
        schedule();
      };
    };

    setConn('connecting');
    setSnap(null);
    clock.recvAt = 0;
    fetch(server + '/api/state')
      .then((r) => r.json())
      .then(onSnap)
      .catch((e) => setLastError(String(e?.message || e)));
    connect();

    const ping = setInterval(() => {
      const ws = wsRef.current;
      if (ws && ws.readyState === 1) ws.send('ping');
      if (clock.recvAt && Date.now() - clock.recvAt > STALE_MS) setConn('offline');
      else if (!clock.recvAt && ws?.readyState !== 1) setConn((c) => (c === 'connecting' ? c : 'offline'));
    }, 5_000);

    const sub = AppState.addEventListener('change', (st) => {
      if (st === 'active' && (!wsRef.current || wsRef.current.readyState !== 1)) {
        if (retry) clearTimeout(retry);
        retry = null;
        backoff = 1000;
        connect();
      }
    });

    return () => {
      alive = false;
      if (retry) clearTimeout(retry);
      clearInterval(ping);
      sub.remove();
      try {
        wsRef.current?.close();
      } catch {
        /* ignore */
      }
      wsRef.current = null;
    };
  }, [server, enabled]);

  return { snap, conn, lastError };
}
