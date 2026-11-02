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

# Розподіл похибки курсу (град., 20 квантилів) за джерелом курсу — бектест журналу 26.10–02.11: курс, що показувала мапа,
# проти того, куди ціль назвали далі (через 3–40 хв). Старе правило «курс ±18° на дім» ловило лише 42% реальних
# наближень; ймовірність із цього розподілу відкалібрована на відкладеній половині даних (0.48 проти 0.51, 0.19/0.14, 0.10/0.08).
HD_Q = {"channels": [0, 0, 0, 0, 0, 5, 7, 10, 14, 19, 22, 28, 32, 42, 50, 56, 63, 82, 93, 145],
        "learned": [0, 0, 0, 0, 0, 0, 0, 0, 12, 14, 18, 19, 25, 26, 29, 46, 55, 69, 78, 110],
        "movement": [4, 6, 7, 7, 10, 13, 13, 23, 26, 26, 34, 36, 76, 94, 97, 97, 97, 156, 158, 164],
        "all": [0, 0, 0, 0, 0, 4, 7, 12, 14, 18, 22, 26, 32, 42, 49, 56, 71, 88, 97, 150]}
NEAR_KM = 15
P_PRE, P_THREAT = 0.15, 0.4  # як в Ізраїлі: широке попередження («можливо, будьте поруч з укриттям») і вузька загроза


def p_toward(hd_src: str | None, delta: float, d_km: float) -> float:
    """Ймовірність, що ціль пройде в межах NEAR_KM від дому, якщо дім на delta° від показаного курсу на відстані d_km."""
    q = HD_Q.get({"from": "movement", "course": "all"}.get(hd_src or "", hd_src or ""), HD_Q["all"])
    w = math.degrees(math.atan(NEAR_KM / max(d_km, NEAR_KM)))
    return sum(0.5 * (abs(delta - e) <= w) + 0.5 * (abs(delta + e) <= w) for e in q) / len(q)


class Push:
    def __init__(self, path: Path = DB) -> None:
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS subs(token TEXT PRIMARY KEY, lon REAL, lat REAL, t REAL)")
        self.db.commit()
        self.fired: dict[tuple, float] = {}
        self.armed: dict[str, dict[str, float]] = {}  # телефон → цілі, про які вже була «загроза» (для явного відбою)
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
    def assess(tr: dict, H: tuple[float, float]) -> dict | None:
        """Оцінка для дому: {d, eta, side, p, stage}: stage «threat» (маршрут поруч або P≥0.4), «pre» (P≥0.15), None."""
        P = to_xy(tr["lat"], tr["lon"])
        d = dist_km(H, P)
        if d > 150:
            return None
        side = FROM[round(bearing(H, P) / 45) % 8]
        base = Push.threat(tr, H)
        if base and base[1] is not None and tr.get("route"):
            return {"d": d, "eta": base[1], "side": side, "p": 1.0, "stage": "threat"}
        hd = tr.get("hd")
        if hd is None:
            return None
        delta = abs((bearing(P, H) - hd + 180) % 360 - 180)
        p = p_toward(tr.get("hd_src"), delta, d)
        eta = d / max(30, tr["speed"]) * 60
        if eta > 45:
            return None
        stage = "threat" if p >= P_THREAT else ("pre" if p >= P_PRE else None)
        return {"d": d, "eta": eta, "side": side, "p": round(p, 2), "stage": stage} if stage else {"d": d, "eta": None, "side": side, "p": round(p, 2), "stage": None, "delta": delta}

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
        """Ізраїльська схема етапів: «можлива загроза» (широко) → «курс на ваш район» (вузько) → явний «відбій для вас».
        Уроки: під час масованої атаки — одне зведене повідомлення на телефон за раз (800 полігонів поклали cell broadcast);
        після загрози — явне «можна виходити», а не тиша (Home Front Command, червень 2025)."""
        subs = self.db.execute("SELECT token, lon, lat FROM subs").fetchall()
        if not subs:
            return
        now = time.time()
        tracks = {t["id"]: t for t in snap["tracks"]}
        live = [t for t in snap["tracks"] if t["status"] == "active" and t["conf"] >= 0.5]
        out = []
        for token, lon, lat in subs:
            H = to_xy(lat, lon)
            new_thr, new_pre = [], []
            for tr in live:
                a = self.assess(tr, H)
                if not a or not a["stage"]:
                    continue
                key = (token, tr["id"], a["stage"])
                last = self.fired.get(key)
                self.fired[key] = now
                if a["stage"] == "threat":
                    self.armed.setdefault(token, {})[tr["id"]] = now
                if last and now - last < REARM:
                    continue
                if a["stage"] == "pre" and self.fired.get((token, tr["id"], "threat"), 0) > now - REARM:
                    continue  # уже попередили сильніше
                (new_thr if a["stage"] == "threat" else new_pre).append((tr, a))
            msg = self._compose(new_thr, new_pre)
            if msg:
                out.append({"to": token, "title": msg[0], "body": msg[1], "sound": "default", "priority": "high",
                            "channelId": "threats", "data": {"track": msg[2]}})
            # відбій для вас: усі цілі, що загрожували, зникли або віддаляються
            arm = self.armed.get(token) or {}
            if arm and not new_thr:
                gone, silent = [], []
                for tid in list(arm):
                    tr = tracks.get(tid)
                    # «зникла з повідомлень» (lost) — НЕ відбій: шахед може летіти мовчки між постами каналів.
                    # Відбій лише з доказом: канали написали «збито / не фіксується» (closed) або ціль явно віддаляється.
                    if tr is None or tr["status"] == "lost":
                        silent.append(tid)
                        continue
                    if tr["status"] == "closed":
                        gone.append(tid)
                        continue
                    a = self.assess(tr, H)
                    if a is not None and a["stage"] is None and a.get("delta", 0) > 90:
                        gone.append(tid)
                if silent and len(silent) + len(gone) == len(arm) and now - max(arm.values()) > 1800:
                    self.armed.pop(token, None)  # пів години без новин — тихо забуваємо, але «відбою» не обіцяємо
                elif gone and len(gone) == len(arm) and now - max(arm.values()) > 120:
                    self.armed.pop(token, None)
                    out.append({"to": token, "title": "Цілі, що йшли до вас, віддалились",
                                "body": "За повідомленнями каналів цілі, що летіли у ваш бік, віддаляються або більше не фіксуються. "
                                        "Офіційний відбій — лише за сиреною та «Повітряною тривогою».",
                                "sound": "default", "channelId": "threats", "data": {}})
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

    @staticmethod
    def _compose(thr: list, pre: list) -> tuple[str, str, str] | None:
        """Одне повідомлення на телефон за тік, навіть коли цілей багато."""
        if thr:
            thr.sort(key=lambda x: x[1]["eta"] if x[1]["eta"] is not None else 999)
            tr, a = thr[0]
            n = sum(t.get("count") or 1 for t, _ in thr)
            title = (f"{NAME.get(tr['type'], 'Ціль')}" + (f" ×{tr['count']}" if (tr.get("count") or 1) > 1 else "")
                     + " — курс на ваш район") if len(thr) == 1 else f"{n} цілей — курс на ваш район"
            body = f"{round(a['d'])} км з {a['side']}" + (f" · ~{max(1, round(a['eta']))} хв" if a["eta"] is not None else "") + \
                (f" · → {tr['next']}" if tr.get("next") else "") + (f" · ймовірність {round(a['p'] * 100)}%" if a["p"] < 1 else "")
            return title, body, tr["id"]
        if pre:
            pre.sort(key=lambda x: -x[1]["p"])
            tr, a = pre[0]
            title = "Можлива загроза: будьте поруч з укриттям"
            body = (f"{NAME.get(tr['type'], 'Ціль')} за {round(a['d'])} км з {a['side']}, ймовірність пройти поруч ~{round(a['p'] * 100)}%"
                    + (f"; ще {len(pre) - 1}" if len(pre) > 1 else "") + ". Це ще не тривога — може й не дійти.")
            return title, body, tr["id"]
        return None
