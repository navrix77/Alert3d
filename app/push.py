"""Push-сповіщення на телефон навіть із заблокованим екраном (Expo Push Service).

Телефон реєструє свій Expo-токен і дім (координати округлені до ~1 км — точна адреса серверу не потрібна).
Сервер сам стежить за цілями і шле сповіщення, коли підтверджена ціль маршрутом або курсом іде на дім.
"""
from __future__ import annotations

import asyncio
import logging
import math
import re
import sqlite3
import time
from pathlib import Path

import httpx

from .geo import bearing, dist_km, to_xy

log = logging.getLogger("push")
DB = Path(__file__).resolve().parent.parent / "data" / "push.sqlite"
TOKEN_RX = re.compile(r"^(ExponentPushToken|ExpoPushToken)\[[A-Za-z0-9_\-]{10,}\]$")
FROM = ["півночі", "північного сходу", "сходу", "південного сходу", "півдня", "південного заходу", "заходу", "північного заходу"]
NAME = {"shahed": "Шахед", "jet": "Реактивний БпЛА", "molniya": "«Молнія»", "cruise": "Крилата ракета", "ballistic": "Балістика"}
REARM = 600  # повтор по тій самій цілі — не раніше ніж за 10 хв після зникнення загрози


class Push:
    def __init__(self, path: Path = DB) -> None:
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS subs(token TEXT PRIMARY KEY, lon REAL, lat REAL, t REAL)")
        self.db.commit()
        self.fired: dict[tuple[str, str], float] = {}
        self.sent = 0

    def register(self, token: str, lon: float, lat: float) -> bool:
        if not TOKEN_RX.match(token or "") or not (20 < lon < 42 and 43 < lat < 53):
            return False
        self.db.execute("INSERT INTO subs VALUES(?,?,?,?) ON CONFLICT(token) DO UPDATE SET lon=excluded.lon, lat=excluded.lat, t=excluded.t",
                        (token, round(lon, 2), round(lat, 2), time.time()))
        self.db.commit()
        return True

    def unregister(self, token: str) -> None:
        self.db.execute("DELETE FROM subs WHERE token=?", (token,))
        self.db.commit()

    def count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM subs").fetchone()[0]

    @staticmethod
    def threat(tr: dict, H: tuple[float, float]) -> tuple[float, float | None, str] | None:
        """Порт homeRel із web/app.js: (відстань, хвилини, «з якого боку») або None."""
        P = to_xy(tr["lat"], tr["lon"])
        d = dist_km(H, P)
        path = [P] + [to_xy(la, lo) for lo, la in tr.get("route") or []]
        acc, best, cum = 0.0, 1e9, 0.0
        for a, b in zip(path, path[1:]):
            vx, vy = b[0] - a[0], b[1] - a[1]
            L2 = vx * vx + vy * vy
            t = max(0.0, min(1.0, ((H[0] - a[0]) * vx + (H[1] - a[1]) * vy) / L2)) if L2 else 0.0
            q = (a[0] + vx * t, a[1] + vy * t)
            dd = dist_km(H, q)
            if dd < best:
                best, cum = dd, acc + math.sqrt(L2) * t
            acc += math.sqrt(L2)
        side = FROM[round(bearing(H, P) / 45) % 8]
        if best < 15 and d < 150 and cum / tr["speed"] * 60 <= 45:
            return d, cum / tr["speed"] * 60, side
        hd = tr.get("hd")
        if hd is not None and d < 150 and abs((bearing(P, H) - hd + 180) % 360 - 180) < 18:
            return d, d / tr["speed"] * 60, side
        return None

    async def run(self, get_state) -> None:
        async with httpx.AsyncClient(timeout=15) as cli:
            while True:
                await asyncio.sleep(5)
                try:
                    await self.tick(cli, get_state())
                except Exception as e:  # noqa: BLE001
                    log.warning("push tick: %s", e)

    async def broadcast(self, title: str, body: str, data: dict | None = None) -> None:
        subs = [r[0] for r in self.db.execute("SELECT token FROM subs").fetchall()]
        if not subs:
            return
        msgs = [{"to": t, "title": title, "body": body, "sound": "default", "data": data or {}} for t in subs]
        async with httpx.AsyncClient(timeout=15) as cli:
            for i in range(0, len(msgs), 100):
                await cli.post("https://exp.host/--/api/v2/push/send", json=msgs[i:i + 100],
                               headers={"Accept": "application/json", "Content-Type": "application/json"})

    async def tick(self, cli: httpx.AsyncClient, snap: dict) -> None:
        subs = self.db.execute("SELECT token, lon, lat FROM subs").fetchall()
        if not subs:
            return
        now = time.time()
        live = [t for t in snap["tracks"] if t["status"] == "active" and t["conf"] >= 0.5]
        out = []
        for token, lon, lat in subs:
            H = to_xy(lat, lon)
            for tr in live:
                r = self.threat(tr, H)
                key = (token, tr["id"])
                if not r:
                    continue
                last = self.fired.get(key)
                self.fired[key] = now
                if last and now - last < REARM:
                    continue
                d, eta, side = r
                n = f" ×{tr['count']}" if (tr.get("count") or 1) > 1 else ""
                title = f"{NAME.get(tr['type'], 'Ціль')}{n} — курс на ваш район"
                body = f"{round(d)} км з {side}" + (f" · ~{max(1, round(eta))} хв" if eta is not None else "") + (f" · → {tr['next']}" if tr.get("next") else "")
                out.append({"to": token, "title": title, "body": body, "sound": "default", "priority": "high",
                            "channelId": "threats", "data": {"track": tr["id"]}})
        # прибрати старі ключі
        self.fired = {k: v for k, v in self.fired.items() if now - v < 3 * REARM}
        for i in range(0, len(out), 100):
            r = await cli.post("https://exp.host/--/api/v2/push/send", json=out[i:i + 100],
                               headers={"Accept": "application/json", "Content-Type": "application/json"})
            self.sent += len(out[i:i + 100])
            try:
                for msg, res in zip(out[i:i + 100], r.json().get("data", [])):
                    if res.get("details", {}).get("error") == "DeviceNotRegistered":
                        self.unregister(msg["to"])
            except Exception:  # noqa: BLE001
                pass
