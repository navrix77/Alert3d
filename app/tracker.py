"""Трекер: склеює спостереження в треки цілей, рахує позицію, курс, маршрут і рівні областей."""
from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field

from .geo import Place, ang_diff, bearing, dist_km, from_xy, move, oblasts
from .launch import LaunchBook
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
    place: Place | None = None
    est: bool = False  # позиція оцінена (не названа каналом)


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
    credited: set[str] = field(default_factory=set)
    pred_src: str | None = None
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
        # без названого пункту не «відводимо» ціль далеко: максимум ~4 хв польоту від останньої фіксації
        return move((self.last.x, self.last.y), self.heading, min(km, self.speed * 4 / 60))


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
    def __init__(self, sources: dict[str, Source], brain=None, learn: bool = True) -> None:
        self.sources = sources
        self.brain = brain
        self.learn = learn
        self.tracks: list[Track] = []
        self.zones: list[Zone] = []
        self.counters: dict[str, int] = {}
        self.log: list[dict] = []
        self.last_update = 0.0
        self.launches = LaunchBook(brain)
        self.exclude: set[str] = set()
        self.prefer: str | None = None

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
            from .config import CHANNEL_REGION
            reg = CHANNEL_REGION.get(src)
            obl = oblasts()
            for tr in self.tracks:
                if tr.closed or (obs.type and tr.type != obs.type):
                    continue
                e = tr.est(t)
                if places and not any(dist_km(p.place.xy, e) < 45 for p in places):
                    continue
                if not places:
                    # «не фіксується» без місця: лише цілі регіону цього каналу (або ті, про які він сам писав)
                    la, lo = from_xy(*e)
                    if not (src in tr.srcs or (reg and obl.of(lo, la) == reg)):
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
        real = next((p for p in places if p.role == "p"), None)
        frm = next((p for p in places if p.role == "f"), None)
        targets = [p.place for p in places if p.role == "t"]
        only_target = real is None and frm is None  # «курсом на X» без поточного місця
        pos = real or (frm if frm and not targets else None) or (places[0] if not targets else None)
        route = [p for p in targets if not pos or p.name != pos.place.name]
        course_to = route[-1].name if route else None
        names = {p.name for p in route}
        if pos is not None:
            pt = pos.place.xy
            tr = self._best(obs.type, pt, t, names)
        else:
            pt = None
            tr = self._best_by_target(obs.type, route, t)
        if tr:
            if pt is not None:
                d = dist_km((tr.last.x, tr.last.y), pt)
                dt = t - tr.last.t
                nom = TYPES[tr.type]["speed"]
                if dt >= 240 and d > 2 and not tr.last.est:
                    meas = d / dt * 3600
                    if nom * 0.5 < meas < nom * 1.6:
                        tr.speed = tr.speed * 0.5 + meas * 0.5
                prev = tr.last
                tr.obs.append(Point(t, pt[0], pt[1], src, pos.place.name, link, pos.place))
                if self.brain and self.learn and prev.place:
                    self.brain.learn_step(tr.type, prev.place, pos.place, 0.6 if prev.est else 1.0)
                if d > 3 and not route and obs.course is None:
                    tr.heading = bearing((prev.x, prev.y), pt)
            elif route:
                # «на X» від каналу, що веде ціль щохвилини: ціль уже біля X (так показують провідні сервіси).
                # Переносимо її в X, якщо X досяжний за час від останньої фіксації; курс — звідки прийшла.
                X = route[0]
                e = tr.est(t)
                reach = tr.speed * max(60.0, t - tr.last.t) / 3600 * 1.6 + 12
                if dist_km(e, X.xy) <= reach:
                    prev = tr.last
                    tr.obs.append(Point(t, X.xy[0], X.xy[1], src, X.name, link, X, True))
                    if dist_km((prev.x, prev.y), X.xy) > 3:
                        tr.heading = bearing((prev.x, prev.y), X.xy)
                    route = route[1:]
            if route:
                # пункт, до якого понад годину польоту, — це тезка з іншого кінця країни, не маршрут цієї цілі
                here = tr.est(t)
                route = [p for p in route if dist_km(here, p.xy) <= min(tr.speed * 1.0 + 60, 260 if tr.type == "shahed" else 900)]
            if route:
                # ціль змінила пункт призначення: послідовність «курсом на A» → «курсом на B» теж маршрут
                old = tr.route[0] if tr.route else None
                if self.brain and self.learn and old and old.name not in names:
                    self.brain.learn_step(tr.type, old, route[0], 0.7)
                tr.route = route
            elif pt is not None:
                tr.route = [p for p in tr.route if dist_km(p.xy, pt) > 3]
            tr.route = [p for p in tr.route if dist_km(p.xy, (tr.last.x, tr.last.y)) > 1.5]
            if tr.route:
                tr.heading = bearing((tr.last.x, tr.last.y), tr.route[0].xy)
            elif obs.course is not None:
                tr.heading = obs.course
        else:
            c = self.counters[obs.type] = self.counters.get(obs.type, 0) + 1
            tr = Track(f"{TYPES[obs.type]['label']}-{c}", obs.type, TYPES[obs.type]["speed"])
            if pos is not None:
                tr.obs.append(Point(t, pt[0], pt[1], src, pos.place.name, link, pos.place))
            else:
                # немає поточного місця: ставимо ціль у найімовірніший попередній пункт (вивчено з історії),
                # інакше — у сам пункт призначення з невідомим курсом
                X = route[0]
                prev = None  # оцінка «звідки» за статистикою ставила різні цілі в одну точку — вимкнено
                if prev:
                    from .geo import to_xy
                    px, py = to_xy(prev[2], prev[3])
                    tr.obs.append(Point(t, px, py, src, prev[0] + " (оцінка)", link, None, True))
                    tr.pred_src = "learned-origin"
                else:
                    tr.obs.append(Point(t, X.xy[0], X.xy[1], src, X.name, link, X, True))
            tr.route = [p for p in route if dist_km(p.xy, (tr.last.x, tr.last.y)) > 2]
            if tr.route:
                tr.heading = bearing((tr.last.x, tr.last.y), tr.route[0].xy)
            elif obs.course is not None:
                tr.heading = obs.course
            elif frm and pos is not None and dist_km(frm.place.xy, pt) > 3:
                tr.heading = bearing(frm.place.xy, pt)
            tr.from_place = frm.place if frm else None
            self.tracks.append(tr)
        # канал прямо назвав «звідки → куди»: це теж знання про маршрут
        if self.brain and self.learn and real is not None and route:
            self.brain.learn_step(obs.type, real.place, route[0], 0.5)
        # довіра: друге незалежне джерело підтверджує всіх, хто вже повідомив про цю ціль
        if src not in tr.srcs and tr.srcs and self.brain and self.learn:
            for s_ in list(tr.srcs) + [src]:
                if s_ not in tr.credited:
                    self.brain.rel_update(s_, True)
                    tr.credited.add(s_)
        tr.srcs.add(src)
        if course_to:
            tr.course_to = course_to
        if obs.count:
            tr.count = max(tr.count or 0, obs.count) if t - tr.obs[0].t < 900 else obs.count
        rec["track"] = tr.id
        return rec

    def _best_by_target(self, typ: str, route, t: float) -> Track | None:
        """Повідомлення без позиції («курсом на X») приєднуємо до треку з тим самим пунктом призначення
        або до треку, з якого X досяжний за час, що минув."""
        if not route:
            return None
        names = {p.name for p in route}
        best, bs = None, 1e9
        for tr in self.tracks:
            if tr.type != typ or tr.closed or t - tr.last.t > TYPES[typ]["life"] or tr.id in self.exclude:
                continue
            shared = names & ({p.name for p in tr.route} | ({tr.course_to} if tr.course_to else set()))
            e = tr.est(t)
            d = min(dist_km(e, p.xy) for p in route)
            if tr.id == self.prefer and d < 80:
                return tr  # канал прямо пише «далі …» про ту саму ціль
            if not shared:
                # нова ціль-пункт має бути попереду (за курсом) і досяжна приблизно за 15 хв
                if d > min(35, tr.speed * 0.25 + 15):
                    continue
                if tr.heading is not None and not tr.last.est and d > 8 and ang_diff(tr.heading, bearing(e, route[0].xy)) > 75:
                    continue
            s = d - (40 if shared else 0)
            if s < bs:
                best, bs = tr, s
        return best

    def _best(self, typ: str, pt, t: float, names: set | None = None) -> Track | None:
        best, bs = None, 1e9
        for tr in self.tracks:
            if tr.type != typ or tr.closed or tr.id in self.exclude:
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
            if names and names & ({p.name for p in tr.route} | ({tr.course_to} if tr.course_to else set())):
                s -= 15  # той самий пункт призначення — найімовірніше та сама ціль
            if s < bs:
                best, bs = tr, s
        return best

    def life(self, tr: Track) -> float:
        """Скільки ціль лишається «активною» без нових повідомлень. Долетіла до названого пункту і мовчить —
        прибираємо через 10 хв (як провідні сервіси), а не тримаємо 40 хв на місці."""
        base = TYPES[tr.type]["life"]
        if tr.route:
            km = sum(dist_km(a, b) for a, b in itertools.pairwise(tr.path()))
            return min(base, km / tr.speed * 3600 + 600)
        return min(base, 600 if tr.last.est or tr.heading is None else 900)

    # ---------------- знімок стану для клієнтів
    def conf(self, tr: Track) -> float:
        q = 1.0
        for s in tr.srcs:
            prior = self.sources.get(s, Source(s, s, 0.5)).rel
            q *= 1 - (self.brain.rel(s, prior) if self.brain else prior)
        return 1 - q

    def snapshot(self, now: float | None = None) -> dict:
        now = now or time.time()
        obl = oblasts()
        out, levels = [], {}

        def up(name, v):
            if name and levels.get(name, 0) < v:
                levels[name] = v

        keep = []
        for tr in self.tracks:
            if now - tr.last.t < TYPES[tr.type]["life"] + 1800:
                keep.append(tr)
            elif self.brain and self.learn and len(tr.srcs) == 1 and not tr.credited:
                self.brain.rel_update(next(iter(tr.srcs)), False, 0.5)  # ніхто не підтвердив
        self.tracks = keep
        for tr in self.tracks:
            life = self.life(tr)
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
            pred_src, pred_p = ("channels" if rest else tr.pred_src), None
            if not rest and status == "active" and self.brain:
                base = tr.last.place.name if tr.last.place else None
                if base:
                    la0, lo0 = from_xy(ex, ey)
                    nx = self.brain.next_places(tr.type, base, tr.heading, (la0, lo0))
                    if nx and nx[0][1] >= 0.3:
                        from .geo import to_xy
                        rest = [to_xy(nx[0][2], nx[0][3])]
                        names = [nx[0][0]]
                        pred_src, pred_p = "learned", round(nx[0][1], 2)
            hd = bearing((ex, ey), rest[0]) if rest else tr.heading
            if hd is None and len(tr.obs) >= 2:  # курс за останніми двома точками
                a_, b_ = tr.obs[-2], tr.obs[-1]
                if dist_km((a_.x, a_.y), (b_.x, b_.y)) > 2:
                    hd = bearing((a_.x, a_.y), (b_.x, b_.y))
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
                "speed": round(tr.speed), "conf": round(conf, 2), "next": names[0] if names else tr.course_to, "route_names": names[:8], "pred": pred_src, "pred_p": pred_p, "pos_est": tr.last.est,
                "route": [[round(from_xy(*p)[1], 4), round(from_xy(*p)[0], 4)] for p in rest[:8]],
                "trail": [[round(from_xy(o.x, o.y)[1], 4), round(from_xy(o.x, o.y)[0], 4), int(o.t)] for o in tr.obs[-6:]],
                "first": int(tr.obs[0].t), "last": int(tr.last.t), "srcs": sorted(tr.srcs),
                "links": [o.link for o in tr.obs[-5:] if o.link],
                "from": tr.from_place.name if tr.from_place else None, "ts": now,
                "entry": [round(from_xy(tr.obs[0].x, tr.obs[0].y)[1], 4), round(from_xy(tr.obs[0].x, tr.obs[0].y)[0], 4), tr.obs[0].label, int(tr.obs[0].t)],
                "launch": self.launches.link(tr, now, hd) if status != "closed" or age < 1800 else None,
            })
        zones = []
        self.zones = [z for z in self.zones if now - z.t < ZONE_LIFE]
        for z in self.zones:
            zones.append({"places": [[p.lon, p.lat, p.name] for p in z.places], "t": int(z.t), "platform": z.platform})
            for p in z.places:
                up(obl.of(p.lon, p.lat), 2)
        return {"now": now, "tracks": out, "zones": zones, "launches": self.launches.snapshot(now), "levels_tracker": levels, "last_update": self.last_update,
                "log": self.log[-60:]}
