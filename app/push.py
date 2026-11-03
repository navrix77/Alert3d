"""Push-сповіщення на телефон навіть із заблокованим екраном (Expo Push Service).

Телефон реєструє свій Expo-токен і дім (координати округлені до ~1 км, точна адреса серверу не потрібна).
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
import json as _json

from .geo import bearing, dist_km, to_xy

log = logging.getLogger("push")
DB = Path(__file__).resolve().parent.parent / "data" / "push.sqlite"
TOKEN_RX = re.compile(r"^(ExponentPushToken|ExpoPushToken)\[[A-Za-z0-9_\-]{10,}\]$")
FROM = ["півночі", "північного сходу", "сходу", "південного сходу", "півдня", "південного заходу", "заходу", "північного заходу"]
NAME = {"shahed": "Шахед", "jet": "Реактивний БпЛА", "molniya": "«Молнія»", "cruise": "Крилата ракета", "ballistic": "Балістика",
        "geran5": "«Герань-5»", "banderol": "«Бандероль»", "rszv": "РСЗВ", "fpv": "FPV-дрон", "fpvf": "FPV на оптоволокні",
        "recon": "Дрон-розвідник", "lancet": "«Ланцет»"}
COMPASS = ["на північ", "на північний схід", "на схід", "на південний схід", "на південь", "на південний захід", "на захід", "на північний захід"]


ZONE_GAP = 300  # не частіше одного зонального зведення на пристрій за 5 хв (масована атака — не спам)
ZONE_AHEAD = (5, 10, 15)  # хв: ціль, що за цей час увійде в зону, теж «у зоні»
_HROM = None


def _hromadas():
    """Межі громад (індекс = номер у hromadas.geojson, як на сайті): [(назва, полігони, bbox)]."""
    global _HROM
    if _HROM is None:
        fc = _json.loads((Path(__file__).resolve().parent.parent / "data" / "hromadas.geojson").read_text(encoding="utf-8"))
        out = []
        for f in fc["features"]:
            g = f["geometry"]
            polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
            xs = [p[0] for pl in polys for p in pl[0]]
            ys = [p[1] for pl in polys for p in pl[0]]
            out.append((f["properties"].get("n", ""), polys, (min(xs), min(ys), max(xs), max(ys))))
        _HROM = out
    return _HROM


def _in_ring(r, x, y) -> bool:
    c = False
    j = len(r) - 1
    for i in range(len(r)):
        a, b = r[i], r[j]
        if (a[1] > y) != (b[1] > y) and x < (b[0] - a[0]) * (y - a[1]) / ((b[1] - a[1]) or 1e-12) + a[0]:
            c = not c
        j = i
    return c


def zone_of(lon: float, lat: float, zones: dict) -> str | None:
    if zones.get("obl"):
        from .geo import oblasts
        o = oblasts().of(lon, lat)
        if o and o in zones["obl"]:
            return f"{o} обл."
    for h in zones.get("hrom") or []:
        H = _hromadas()
        if 0 <= h < len(H):
            n, polys, bb = H[h]
            if bb[0] <= lon <= bb[2] and bb[1] <= lat <= bb[3] and any(_in_ring(pl[0], lon, lat) for pl in polys):
                return f"{n} громада"
    return None


def _ahead(tr: dict, minutes: float) -> tuple[float, float]:
    """Де буде ціль через N хв: уздовж названого маршруту, інакше курсом; швидкість як на мапі (≈0.7 паспортної)."""
    from .geo import bearing, from_xy, move
    P = to_xy(tr["lat"], tr["lon"])
    km = (tr.get("speed") or 170) * 0.7 * minutes / 60
    if tr.get("route"):
        Q = to_xy(tr["route"][0][1], tr["route"][0][0])
        hd = bearing(P, Q)
    elif tr.get("hd") is not None:
        hd = tr["hd"]
    else:
        return tr["lon"], tr["lat"]
    la, lo = from_xy(*move(P, hd, km))
    return lo, la


def _hm(t) -> str:
    return time.strftime("%H:%M", time.localtime(t)) if t else "?"


def _who(tr: dict) -> str:
    """Доказовість одним рядком: скільки незалежних джерел і коли останнє місце від каналів."""
    ev = tr.get("ev") or {}
    n = len(ev.get("prim") or []) or len(tr.get("srcs") or []) or 1
    at = tr.get("at")
    return (f"{n} незалежн{'е джерело' if n == 1 else 'і джерела' if n < 5 else 'их джерел'}"
            + (f" · місце о {_hm(at[1])}" if at else f" · оновлено о {_hm(tr.get('last'))}"))


def _rel(a: dict) -> str:
    """«12 км на захід від вас» (assess дає сторону в родовому: «заходу»)."""
    side = COMPASS[FROM.index(a["side"])] if a.get("side") in FROM else ""
    return f"{max(1, round(a['d']))} км {side} від вас".replace("  ", " ")


def _where(tr: dict, a: dict) -> str:
    if a.get("d") is None:
        return ""  # без службових пояснень: лише те, що допомагає вирішити
    at = tr.get("at")
    return (f"{at[0]}, " if at else "") + _rel(a).replace(" від вас", " від вас")  # коротко, як на екрані блокування: «Люботин, 12 км на захід від вас»


def _move(tr: dict) -> str:
    hd = tr.get("hd")
    parts = []
    if tr.get("next"):
        parts.append(f"Курс → {tr['next']}")
    if hd is not None:
        parts.append(("ймовірно " if not tr.get("next") else "") + COMPASS[round(hd / 45) % 8])
    return " · ".join(parts)

VAPID_KEY = DB.parent / "vapid_private.pem"  # ключ сервера для Web Push (браузер/PWA/iPhone з початкового екрана)
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
        # Web Push: сайт і PWA (Android Chrome, Windows, iPhone з «На початковий екран») — сповіщення навіть із закритим браузером
        self.db.execute("CREATE TABLE IF NOT EXISTS websubs(endpoint TEXT PRIMARY KEY, sub TEXT, lon REAL, lat REAL, t REAL)")
        try:  # «лише курс на ваш район» — без ранніх «можлива загроза» (менше сповіщень)
            self.db.execute("ALTER TABLE websubs ADD COLUMN pre INTEGER DEFAULT 1")
        except sqlite3.OperationalError:
            pass
        try:  # обрані області й громади ({"obl": [назви], "hrom": [індекси громад у hromadas.geojson]})
            self.db.execute("ALTER TABLE websubs ADD COLUMN zones TEXT")
        except sqlite3.OperationalError:
            pass
        self.db.commit()
        self._vapid = None
        self.web_sender = None  # для тестів: підміна відправлення
        self.fired: dict[tuple, float] = {}
        self.armed: dict[str, dict[str, float]] = {}  # телефон → цілі, про які вже була «загроза» (для явного відбою)
        self.zseen: dict[tuple, float] = {}  # (пристрій, ціль) → коли сповістили про ціль у його зоні
        self.zlast: dict[str, float] = {}  # пристрій → коли надіслали останнє зональне зведення
        self.sent = 0

    def register(self, token: str, lon: float, lat: float) -> bool:
        if not TOKEN_RX.match(token or "") or not (20 < lon < 42 and 43 < lat < 53):
            return False
        self.db.execute("INSERT INTO subs VALUES(?,?,?,?) ON CONFLICT(token) DO UPDATE SET lon=excluded.lon, lat=excluded.lat, t=excluded.t",
                        (token, round(lon, 2), round(lat, 2), time.time()))
        self.db.commit()
        return True

    # ---------- Web Push ----------
    def vapid(self):
        if self._vapid is None:
            from py_vapid import Vapid02 as Vapid01  # RFC 8292 «vapid t=…, k=…» — потрібно Apple й іншим
            if VAPID_KEY.exists():
                self._vapid = Vapid01.from_file(str(VAPID_KEY))
            else:
                v = Vapid01()
                v.generate_keys()
                VAPID_KEY.parent.mkdir(parents=True, exist_ok=True)
                v.save_key(str(VAPID_KEY))
                self._vapid = v
        return self._vapid

    def public_key(self) -> str:
        import base64
        from cryptography.hazmat.primitives import serialization
        raw = self.vapid().public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    def web_register(self, sub: dict, lon: float, lat: float, pre: bool = True, zones: dict | None = None) -> bool:
        ep = str((sub or {}).get("endpoint", ""))
        keys = (sub or {}).get("keys") or {}
        if not ep.startswith("https://") or len(ep) > 1000 or not keys.get("p256dh") or not keys.get("auth"):
            return False
        if not (20 < lon < 42 and 43 < lat < 53):
            return False
        z = None
        if isinstance(zones, dict):
            obl = [str(o)[:40] for o in (zones.get("obl") or [])][:25]
            hrom = [int(h) for h in (zones.get("hrom") or []) if str(h).isdigit()][:40]
            z = _json.dumps({"obl": obl, "hrom": hrom}, ensure_ascii=False) if (obl or hrom) else None
        self.db.execute("INSERT INTO websubs(endpoint, sub, lon, lat, t, pre, zones) VALUES(?,?,?,?,?,?,?) ON CONFLICT(endpoint) DO UPDATE SET sub=excluded.sub, lon=excluded.lon, lat=excluded.lat, t=excluded.t, pre=excluded.pre, zones=excluded.zones",
                        (ep, _json.dumps({"endpoint": ep, "keys": {"p256dh": keys["p256dh"], "auth": keys["auth"]}}), round(lon, 2), round(lat, 2), time.time(), 1 if pre else 0, z))
        self.db.commit()
        return True

    def web_unregister(self, endpoint: str) -> None:
        self.db.execute("DELETE FROM websubs WHERE endpoint=?", (endpoint,))
        self.db.commit()

    def _web_send_sync(self, sub: dict, payload: dict) -> int:
        from pywebpush import WebPushException, webpush
        try:
            webpush(subscription_info=sub, data=_json.dumps(payload, ensure_ascii=False), vapid_private_key=self.vapid(),
                    vapid_claims={"sub": "https://sky.navryx.com.ua"}, ttl=600, headers={"Urgency": "high"}, timeout=10)
            return 201
        except WebPushException as e:
            return getattr(e.response, "status_code", 0) or 0

    async def _web_send(self, msgs: list[dict]) -> None:
        for m in msgs:
            payload = {"title": m["title"], "body": m["body"], "tag": (m.get("data") or {}).get("track") or "navryx", "url": "/"}
            # картинка для Android/Windows (iPhone її не показує): ціль на тлі кольору рівня
            lv = {"🔴": "red", "🟠": "orange", "🟡": "yellow", "🟢": "green"}.get(m["title"][:1])
            ty = (m.get("data") or {}).get("type")
            if lv and ty in NAME:
                payload["image"] = f"/notif/{lv}-{ty}.jpg"
            sub = _json.loads(m["sub"])
            code = await (self.web_sender(sub, payload) if self.web_sender else asyncio.to_thread(self._web_send_sync, sub, payload))
            self.sent += 1
            if code in (404, 410):  # підписку скасовано в браузері
                self.web_unregister(sub["endpoint"])

    def unregister(self, token: str) -> None:
        self.db.execute("DELETE FROM subs WHERE token=?", (token,))
        self.db.commit()

    def count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM subs").fetchone()[0] + self.db.execute("SELECT COUNT(*) FROM websubs").fetchone()[0]

    @staticmethod
    def assess(tr: dict, H: tuple[float, float]) -> dict | None:
        """Оцінка для дому: {d, eta, side, p, stage}: stage «threat» (маршрут поруч або P≥0.4), «pre» (P≥0.15), None."""
        P = to_xy(tr["lat"], tr["lon"])
        d = dist_km(H, P)
        if tr.get("nopos"):
            # канали назвали лише курс («на Харків»): де ціль — невідомо. Загроза — лише якщо названий пункт біля дому,
            # без вигаданих «N км» і хвилин
            pts = [to_xy(la, lo) for lo, la in tr.get("route") or []] or [P]
            if any(dist_km(H, q) <= NEAR_KM for q in pts):
                return {"d": None, "eta": None, "side": None, "p": 1.0, "stage": "threat"}
            return None
        if d > 150:
            return None
        side = FROM[round(bearing(H, P) / 45) % 8]
        if d <= NEAR_KM:  # ціль уже поруч — загроза незалежно від курсу (03.11: шахеди за 3–6 км, курс невідомий → push не було)
            return {"d": d, "eta": None, "side": side, "p": 1.0, "stage": "threat"}
        base = Push.threat(tr, H)
        if base and base[1] is not None and tr.get("route"):
            return {"d": d, "eta": None if tr.get("type") in ("ballistic", "rszv") else base[1], "side": side, "p": 1.0, "stage": "threat"}
        hd = tr.get("hd")
        if hd is None:
            return None
        delta = abs((bearing(P, H) - hd + 180) % 360 - 180)
        p = p_toward(tr.get("hd_src"), delta, d)
        # балістика й РСЗВ: «балістика» без відстані й траєкторії пуску не дає підстав для зворотного відліку
        eta = None if tr.get("type") in ("ballistic", "rszv") else d / max(30, tr["speed"]) * 60
        if eta is not None and eta > 45:
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
        web = self.db.execute("SELECT endpoint, sub FROM websubs").fetchall()
        if web:
            await self._web_send([{"to": e, "sub": s_, "title": title, "body": body, "data": data or {}} for e, s_ in web])
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
        Уроки: під час масованої атаки, одне зведене повідомлення на телефон за раз (800 полігонів поклали cell broadcast);
        після загрози, явне «можна виходити», а не тиша (Home Front Command, червень 2025)."""
        subs = self.db.execute("SELECT token, lon, lat FROM subs").fetchall()
        webs = {r[0]: r[1] for r in self.db.execute("SELECT endpoint, sub FROM websubs").fetchall()}
        no_pre = {r[0] for r in self.db.execute("SELECT endpoint FROM websubs WHERE pre=0").fetchall()}
        zmap = {r[0]: _json.loads(r[1]) for r in self.db.execute("SELECT endpoint, zones FROM websubs WHERE zones IS NOT NULL").fetchall()}
        subs += self.db.execute("SELECT endpoint, lon, lat FROM websubs").fetchall()
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
            msg = self._compose(new_thr, [] if token in no_pre else new_pre)
            if msg:
                out.append({"to": token, "title": msg[0], "body": msg[1], "sound": "default", "priority": "high",
                            "channelId": "threats", "data": {"track": msg[2], "type": (tracks.get(msg[2]) or {}).get("type")}})
            # обрані області й громади: нові цілі в зоні (або що увійдуть за ≤15 хв), одним зведенням не частіше разу на 5 хв
            zones = zmap.get(token)
            if zones and not msg:
                homed = {t["id"] for t, _ in new_thr + new_pre}
                cand = []
                for tr in live:
                    if tr.get("nopos") or tr["id"] in homed or (token, tr["id"]) in self.zseen:
                        continue
                    z = zone_of(tr["lon"], tr["lat"], zones)
                    eta = 0
                    if not z:
                        for m in ZONE_AHEAD:
                            z = zone_of(*_ahead(tr, m), zones)
                            if z:
                                eta = m
                                break
                    if z:
                        cand.append((tr, z, eta))
                if cand and now - self.zlast.get(token, 0) >= ZONE_GAP:
                    zm = self._compose_zone(cand)
                    out.append({"to": token, "title": zm[0], "body": zm[1], "sound": "default", "priority": "high",
                                "channelId": "zones", "data": {"track": zm[2], "type": (tracks.get(zm[2]) or {}).get("type")}})
                    self.zlast[token] = now
                    for tr, _z, _e in cand:
                        self.zseen[(token, tr["id"])] = now
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
                    out.append({"to": token, "title": "🟢 Цілі, що йшли до вас, віддалились",
                                "body": "За повідомленнями каналів вони віддаляються або більше не фіксуються.\n"
                                        "Це ще не відбій: офіційний відбій лише за сиреною та «Повітряною тривогою».",
                                "sound": "default", "channelId": "threats", "data": {}})
        self.fired = {k: v for k, v in self.fired.items() if now - v < 3 * REARM}
        self.zseen = {k: v for k, v in self.zseen.items() if now - v < 3600}
        web_out = [dict(m, sub=webs[m["to"]]) for m in out if m["to"] in webs]
        out = [m for m in out if m["to"] not in webs]
        if web_out:
            await self._web_send(web_out)
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
    def _compose_zone(cand: list) -> tuple[str, str, str]:
        """Зведення для обраних областей і громад: уже в зоні — першими, далі ті, що найшвидше увійдуть."""
        cand.sort(key=lambda x: (x[2], -(x[0].get("count") or 1)))
        tr, z, eta = cand[0]
        n = sum(t.get("count") or 1 for t, _z, _e in cand)
        zones = sorted({c[1] for c in cand})
        where = zones[0] if len(zones) == 1 else f"{zones[0]} і ще {len(zones) - 1}"
        nm = NAME.get(tr["type"], "Ціль") + (f" ×{tr['count']}" if (tr.get("count") or 1) > 1 else "")
        if n == 1:
            title = f"🟠 {nm} · " + (f"~{eta} хв до «{z}»" if eta else f"у межах «{z}»")
        else:
            title = f"🟠 {where}: {n} {'нова ціль' if n % 10 == 1 and n % 100 != 11 else 'нові цілі' if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else 'нових цілей'}"
        at = tr.get("at")
        lines = [(f"{nm}: " if n > 1 else "") + (f"останнє місце {at[0]}" if at else "") + (f" · ~{eta} хв до «{z}»" if eta and n > 1 else ""),
                 _move(tr)]
        if len(cand) > 1:
            lines.append("Ще: " + "; ".join(f"{NAME.get(t['type'], 'ціль')}" + (f" → {t['next']}" if t.get("next") else "") for t, _z, _e in cand[1:4])
                         + (f" і ще {len(cand) - 4}" if len(cand) > 4 else ""))
        return title, "\n".join(x.strip(" ·:") for x in lines if x.strip(" ·:")), tr["id"]

    @staticmethod
    def _compose(thr: list, pre: list) -> tuple[str, str, str] | None:
        """Одне повідомлення на телефон за тік, навіть коли цілей багато. Структура однакова для всіх рівнів:
        заголовок — рівень (колір), що і коли; тіло — де зараз, куди летить, на чому ґрунтується, що робити."""
        if thr:
            # першою — найнебезпечніша: уже поруч, далі найменший час підльоту, далі найближча
            thr.sort(key=lambda x: (0 if x[1].get("d") is not None and x[1]["d"] <= NEAR_KM else 1,
                                    x[1]["eta"] if x[1]["eta"] is not None else 999, x[1]["d"] if x[1]["d"] is not None else 999))
            tr, a = thr[0]
            nm = NAME.get(tr["type"], "Ціль") + (f" ×{tr['count']}" if (tr.get("count") or 1) > 1 else "")
            near = a.get("d") is not None and a["d"] <= NEAR_KM
            soon = a["eta"] is not None and a["eta"] <= 10
            lvl = "🔴" if near or soon else "🟠"
            n = sum(t.get("count") or 1 for t, _ in thr)
            if len(thr) > 1:
                title = f"{lvl} {n} {'ціль' if n % 10 == 1 and n % 100 != 11 else 'цілі' if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else 'цілей'} до вас · найближча " + (f"~{max(1, round(a['eta']))} хв" if a["eta"] is not None else f"{round(a['d'])} км" if a.get("d") is not None else "місце невідоме")
            elif a["eta"] is not None and soon:
                title = f"{lvl} {nm} · ~{max(1, round(a['eta']))} хв до вас"
            elif near:
                title = f"{lvl} {nm} поруч · {max(1, round(a['d']))} км"
            elif a["eta"] is not None:
                title = f"{lvl} {nm} · ~{max(1, round(a['eta']))} хв до вас"
            else:
                title = f"{lvl} {nm} · курс на ваш район"
            lines = [_where(tr, a), _move(tr) + (f" · шанс пройти поруч {round(a['p'] * 100)}%" if a["p"] < 1 else "")]
            if len(thr) > 1:
                rest = [f"{NAME.get(t['type'], 'ціль')} " + (_rel(x).replace(" від вас", "") if x.get("d") is not None else "місце невідоме") for t, x in thr[1:3]]
                lines.append("Ще: " + "; ".join(rest) + (f" і ще {len(thr) - 3}" if len(thr) > 3 else ""))
            lines.append("Перейдіть в укриття." if lvl == "🔴" else "Будьте поруч з укриттям.")
            return title, "\n".join(x.strip(" ·") for x in lines if x.strip(" ·")), tr["id"]
        if pre:
            pre.sort(key=lambda x: -x[1]["p"])
            tr, a = pre[0]
            title = f"🟡 Можлива загроза · {NAME.get(tr['type'], 'Ціль')} {round(a['d'])} км"
            lines = [_where(tr, a), _move(tr) + f" · шанс пройти поруч ~{round(a['p'] * 100)}%", f"Ще {len(pre) - 1} поруч" if len(pre) > 1 else "", "Це ще не тривога. Будьте поруч з укриттям."]
            return title, "\n".join(x.strip(" ·") for x in lines if x.strip(" ·")), tr["id"]
        return None
