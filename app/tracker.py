"""Трекер: склеює спостереження в треки цілей, рахує позицію, курс, маршрут і рівні областей."""
from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field

from .geo import Place, ang_diff, bearing, dist_km, from_xy, move, oblasts
from .parser import Observation

TYPES = {
    "shahed": {"label": "Ш", "name": "Шахед/Гербера", "speed": 170, "life": 40 * 60},
    "jet": {"label": "РБ", "name": "Реактивний БпЛА", "speed": 450, "life": 15 * 60},
    "molniya": {"label": "М", "name": "«Молнія»", "speed": 120, "life": 20 * 60},
    "cruise": {"label": "КР", "name": "Крилата ракета", "speed": 800, "life": 12 * 60},
    "ballistic": {"label": "Б", "name": "Балістика", "speed": 2000, "life": 5 * 60},
}
ZONE_LIFE = 12 * 60


@dataclass
class Source:
    key: str
    name: str
    rel: float
    official: bool = False
    url: str | None = None


@dataclass
class Point:
    t: float
    x: float
    y: float
    src: str
    label: str
    link: str | None


@dataclass
class Track:
    id: str
    type: str
    speed: float
    count: int | None = None
    obs: list[Point] = field(default_factory=list)
    route: list[Place] = field(default_factory=list)
    heading: float | None = None
    srcs: set[str] = field(default_factory=set)
    from_place: Place | None = None
    course_to: str | None = None
    closed: float | None = None

    @property
    def last(self) -> Point:
        return self.obs[-1]

    def path(self) -> list[tuple[float, float]]:
        pts = [(self.last.x, self.last.y)]
        for p in self.route:
            if dist_km(pts[-1], p.xy) > 1:
                pts.append(p.xy)
        return pts

    def est(self, now: float) -> tuple[float, float]:
        km = self.speed * max(0.0, now - self.last.t) / 3600
        if self.route:
            return along(self.path(), km)
        if self.heading is None:
            return (self.last.x, self.last.y)
        return move((self.last.x, self.last.y), self.heading, km)


def along(pts: list[tuple[float, float]], km: float) -> tuple[float, float]:
    if km <= 0 or len(pts) == 1:
        return pts[0]
    acc = 0.0
    for a, b in itertools.pairwise(pts):
        d = dist_km(a, b)
        if acc + d >= km:
            f = (km - acc) / (d or 1)
            return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
        acc += d
    return pts[-1]


@dataclass
class Zone:
    places: list[Place]
    t: float
    src: str
    platform: str | None


class Tracker:
    def __init__(self, sources: dict[str, Source]) -> None:
        self.sources = sources
        self.tracks: list[Track] = []
        self.zones: list[Zone] = []
        self.counters: dict[str, int] = {}
        self.log: list[dict] = []
        self.last_update = 0.0

    # ---------------- прийом повідомлення
    def ingest(self, obs: Observation, src: str, t: float | None = None, link: str | None = None) -> dict:
        t = t or time.time()
        self.last_update = max(self.last_update, t)
        rec = {"t": t, "src": src, "kind": obs.kind, "type": obs.type, "count": obs.count, "link": link, "track": None,
               "places": [{"r": r.role, "n": r.place.name} for r in obs.places] if not obs.safety else []}
        self.log.append(rec)
        self.log = self.log[-400:]
        places = obs.places
        if obs.kind == "filtered":
            return rec
        if obs.kind == "close":
            n = 0
            for tr in self.tracks:
                if tr.closed or (obs.type and tr.type != obs.type):
                    continue
                e = tr.est(t)
                if places and not any(dist_km(p.place.xy, e) < 45 for p in places):
                    continue
                tr.closed = t
                n += 1
            rec["closed"] = n
            return rec
        if obs.kind == "zone":
            if places:
                self.zones.append(Zone([p.place for p in places], t, src, "Су-34" if obs.aviation else None))
            return rec
        if obs.kind != "track" or obs.type not in TYPES:
            return rec
        pos = next((p for p in places if p.role == "p"), None) or next((p for p in places if p.role == "t"), None) or places[0]
        frm = next((p for p in places if p.role == "f"), None)
        route = [p.place for p in places if p.role == "t" and p is not pos]
        pt = pos.place.xy
        course_to = pos.place.name if pos.role == "t" and not route else (route[-1].name if route else None)
        tr = self._best(obs.type, pt, t)
        if tr:
            d = dist_km((tr.last.x, tr.last.y), pt)
            dt = t - tr.last.t
            nom = TYPES[tr.type]["speed"]
            if dt >= 240 and d > 2:
                meas = d / dt * 3600
                if nom * 0.5 < meas < nom * 1.6:
                    tr.speed = tr.speed * 0.5 + meas * 0.5
            prev = (tr.last.x, tr.last.y)
            tr.obs.append(Point(t, pt[0], pt[1], src, pos.place.name, link))
            tr.route = route or [p for p in tr.route if dist_km(p.xy, pt) > 3]
            if tr.route:
                tr.heading = bearing(pt, tr.route[0].xy)
            elif obs.course is not None:
                tr.heading = obs.course
            elif d > 3:
                tr.heading = bearing(prev, pt)
        else:
            c = self.counters[obs.type] = self.counters.get(obs.type, 0) + 1
            tr = Track(f"{TYPES[obs.type]['label']}-{c}", obs.type, TYPES[obs.type]["speed"])
            tr.obs.append(Point(t, pt[0], pt[1], src, pos.place.name, link))
            tr.route = route
            if route:
                tr.heading = bearing(pt, route[0].xy)
            elif obs.course is not None:
                tr.heading = obs.course
            elif frm and dist_km(frm.place.xy, pt) > 3:
                tr.heading = bearing(frm.place.xy, pt)
            tr.from_place = frm.place if frm else None
            self.tracks.append(tr)
        tr.srcs.add(src)
        if course_to:
            tr.course_to = course_to
        if obs.count:
            tr.count = obs.count
        rec["track"] = tr.id
        return rec

    def _best(self, typ: str, pt, t: float) -> Track | None:
        best, bs = None, 1e9
        for tr in self.tracks:
            if tr.type != typ or tr.closed:
                continue
            dt = t - tr.last.t
            if dt > TYPES[typ]["life"] * 1.2:
                continue
            last = (tr.last.x, tr.last.y)
            d = dist_km(last, pt)
            if d > tr.speed * dt / 3600 * 1.15 + 18:
                continue
            pen = 0.0
            if tr.heading is not None and d > 15:
                a = ang_diff(tr.heading, bearing(last, pt))
                if a > 110:
                    continue
                pen = a * 0.25
            s = dist_km(tr.est(t), pt) + pen
            if s < bs:
                best, bs = tr, s
        return best

    # ---------------- знімок стану для клієнтів
    def conf(self, tr: Track) -> float:
        q = 1.0
        for s in tr.srcs:
            q *= 1 - self.sources.get(s, Source(s, s, 0.5)).rel
        return 1 - q

    def snapshot(self, now: float | None = None) -> dict:
        now = now or time.time()
        obl = oblasts()
        out, levels = [], {}

        def up(name, v):
            if name and levels.get(name, 0) < v:
                levels[name] = v

        self.tracks = [tr for tr in self.tracks if now - tr.last.t < TYPES[tr.type]["life"] + 1800]
        for tr in self.tracks:
            life = TYPES[tr.type]["life"]
            age = now - tr.last.t
            status = "closed" if tr.closed else ("lost" if age > life else "active")
            if status != "active" and age > life + 900:
                continue
            ex, ey = tr.est(now) if status == "active" else (tr.last.x, tr.last.y)
            lat, lon = from_xy(ex, ey)
            km = tr.speed * min(age, life) / 3600
            rest = []
            if tr.route and status == "active":
                acc = 0.0
                pts = tr.path()
                for a, b in itertools.pairwise(pts):
                    acc += dist_km(a, b)
                    if acc > km + 0.5:
                        rest.append(b)
            names = [p.name for p in tr.route if dist_km(p.xy, (ex, ey)) > 2 and p.xy in rest] or []
            hd = bearing((ex, ey), rest[0]) if rest else tr.heading
            conf = self.conf(tr)
            if status == "active":
                up(obl.of(lon, lat), 2 if conf >= 0.5 else 1)
                if conf >= 0.5:
                    for m in range(2, 16, 2):
                        p = along([(ex, ey)] + rest, tr.speed * m / 60) if rest else (move((ex, ey), hd, tr.speed * m / 60) if hd is not None else None)
                        if p is None:
                            break
                        la, lo = from_xy(*p)
                        up(obl.of(lo, la), 1)
            out.append({
                "id": tr.id, "type": tr.type, "name": TYPES[tr.type]["name"], "count": tr.count, "status": status,
                "lat": round(lat, 5), "lon": round(lon, 5), "hd": None if hd is None else round(hd, 1),
                "speed": round(tr.speed), "conf": round(conf, 2), "next": names[0] if names else tr.course_to,
                "route": [[round(from_xy(*p)[1], 4), round(from_xy(*p)[0], 4)] for p in rest[:8]],
                "trail": [[round(from_xy(o.x, o.y)[1], 4), round(from_xy(o.x, o.y)[0], 4), int(o.t)] for o in tr.obs[-6:]],
                "first": int(tr.obs[0].t), "last": int(tr.last.t), "srcs": sorted(tr.srcs),
                "links": [o.link for o in tr.obs[-5:] if o.link],
                "from": tr.from_place.name if tr.from_place else None, "ts": now,
            })
        zones = []
        self.zones = [z for z in self.zones if now - z.t < ZONE_LIFE]
        for z in self.zones:
            zones.append({"places": [[p.lon, p.lat, p.name] for p in z.places], "t": int(z.t), "platform": z.platform})
            for p in z.places:
                up(obl.of(p.lon, p.lat), 2)
        return {"now": now, "tracks": out, "zones": zones, "levels_tracker": levels, "last_update": self.last_update,
                "log": self.log[-60:]}
