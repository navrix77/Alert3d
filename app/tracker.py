"""Трекер: склеює спостереження в треки цілей, рахує позицію, курс, маршрут і рівні областей."""
from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field

from .geo import Place, ang_diff, bearing, dist_km, from_xy, move, oblasts
import re as _re


def _norm_key(s: str) -> str:
    """Текст без емодзі, підписів і посилань — щоб упізнати перепост."""
    s = s.lower()
    s = _re.sub(r"https?://\S+|@\w+|підпи\w*.*|подпи\w*.*", " ", s)
    s = _re.sub(r"[^а-яіїєґa-z0-9]+", " ", s).strip()
    return s[:90]

from .launch import LaunchBook
from .parser import Observation

TYPES = {
    "shahed": {"label": "Ш", "name": "Шахед/Гербера", "speed": 170, "life": 25 * 60},
    "jet": {"label": "РБ", "name": "Реактивний БпЛА", "speed": 450, "life": 15 * 60},
    "molniya": {"label": "М", "name": "«Молнія»", "speed": 120, "life": 20 * 60},
    "cruise": {"label": "КР", "name": "Крилата ракета", "speed": 800, "life": 8 * 60},
    "ballistic": {"label": "Б", "name": "Балістика", "speed": 2000, "life": 3 * 60},
    "geran5": {"label": "Г5", "name": "«Герань-5»", "speed": 550, "life": 12 * 60},
    "banderol": {"label": "БД", "name": "«Бандероль»", "speed": 700, "life": 8 * 60},
    "rszv": {"label": "РС", "name": "РСЗВ", "speed": 1500, "life": 3 * 60},
    "fpv": {"label": "FPV", "name": "FPV-дрон", "speed": 80, "life": 8 * 60},
    "fpvf": {"label": "FPV", "name": "FPV на оптоволокні", "speed": 60, "life": 8 * 60},
}
FAST_TYPES = ("cruise", "ballistic", "banderol", "rszv", "geran5")
# КАБ: зона живе, поки про неї пишуть або поки біля кордону активна тактична авіація
KAB_QUIET = 10 * 60      # без нових згадок і без авіації — прибираємо
KAB_AVIA = 15 * 60       # авіація активна — максимум 15 хв: КАБ довше не летить, без повторних пусків загрози немає
KAB_MAX = 15 * 60        # жорстка межа від останньої згадки
AVIA_LIFE = 25 * 60      # «активність тактичної авіації» без підтверджень
# типові райони пусків КАБ (носії Су-34/Су-35 тримаються за 40–70 км від цілі, над РФ або окупованою територією)
LAUNCH_AREA = {"Харківська": (50.62, 36.85, "Бєлгородщина"), "Сумська": (51.40, 35.35, "Курщина"),
               "Чернігівська": (52.40, 32.95, "Брянщина"), "Донецька": (48.05, 38.10, "окупована Донеччина"),
               "Луганська": (48.65, 39.35, "окупована Луганщина"), "Запорізька": (47.20, 35.95, "окупована Запорізька"),
               "Дніпропетровська": (47.45, 36.55, "окупована Запорізька"), "Херсонська": (46.50, 33.25, "лівобережжя Херсонщини"),
               "Миколаївська": (46.50, 33.25, "лівобережжя Херсонщини")}
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
    course_xy: tuple | None = None
    credited: set[str] = field(default_factory=set)
    evidence: list = field(default_factory=list)  # [{t, src, link, text, why, dest, pos, key}]
    pred_src: str | None = None
    last_pred: tuple | None = None  # (назва, xy, t) — перший крок навченого прогнозу, для самоперевірки
    closed: float | None = None
    merged: str | None = None  # дублікат іншого треку (той самий об'єкт, різні канали/назви)

    @property
    def last(self) -> Point:
        return self.obs[-1]

    def path(self) -> list[tuple[float, float]]:
        pts = [(self.last.x, self.last.y)]
        for p in self.route:
            if dist_km(pts[-1], p.xy) > 1:
                pts.append(p.xy)
        return pts

    def est(self, now: float, cap_min: float = 4) -> tuple[float, float]:
        km = self.speed * max(0.0, now - self.last.t) / 3600
        if self.route:
            pts = self.path()
            tot = sum(dist_km(pts[i - 1], pts[i]) for i in range(1, len(pts)))
            if km <= tot or self.heading is None:
                return along(pts, km)
            # пункт пройдено — летить далі тим самим курсом, доки не з'явиться нове повідомлення
            hd = bearing(pts[-2], pts[-1]) if len(pts) > 1 else self.heading
            return move(pts[-1], hd, min(km - tot, self.speed * cap_min / 60))
        if self.heading is None:
            return (self.last.x, self.last.y)
        # для зіставлення повідомлень — лише ~4 хв польоту; для показу на карті — довше (зона невизначеності росте)
        return move((self.last.x, self.last.y), self.heading, min(km, self.speed * cap_min / 60))


SHOW_MIN = 25  # скільки хвилин ціль «летить» на карті без нового повідомлення (дрони)
# ракети летять швидко і падають/збиваються за хвилини: далі назваого пункту — лише трохи
SHOW_BY_TYPE = {"shahed": 25, "molniya": 20, "jet": 6, "cruise": 2, "ballistic": 1, "geran5": 5, "banderol": 2, "rszv": 1, "fpv": 5, "fpvf": 5}


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


def obl_of(p) -> str | None:
    try:
        return oblasts().of(p.lon, p.lat)
    except Exception:
        return None


def _obl_name(reg) -> str | None:
    """CHANNEL_REGION → назва області як у oblasts() ("Харківська")."""
    if not reg:
        return None
    r = str(reg)
    for o in LAUNCH_AREA:
        if r.lower().startswith(o[:5].lower()):
            return o
    return None


@dataclass
class Zone:
    places: list[Place]
    t: float
    src: str
    platform: str | None
    last: float = 0.0
    n: int = 1
    obl: str | None = None
    ev: list = field(default_factory=list)  # докази: [{t, src, text, link}]


class Tracker:
    def __init__(self, sources: dict[str, Source], brain=None, learn: bool = True) -> None:
        self.sources = sources
        self.brain = brain
        self.learn = learn
        self.tracks: list[Track] = []
        self.zones: list[Zone] = []
        self.avia: dict[str, dict] = {}  # область -> {"t", "first", "n", "platform"}
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
            # «збито / вибухи / приліт» не публікуємо (безпека), але ціль після цього прибираємо з карти
            fast = FAST_TYPES if obs.type is None else ((obs.type,) if obs.type in TYPES else ())
            if fast:
                done = 0
                for tr in sorted(self.tracks, key=lambda x: -x.last.t):
                    if tr.closed or tr.type not in fast or t - tr.last.t > TYPES[tr.type]["life"]:
                        continue
                    e = tr.est(t)
                    ends = [e] + ([tr.route[-1].xy] if tr.route else [])
                    if places:
                        if not any(dist_km(p.place.xy, q) < 30 for p in places for q in ends):
                            continue
                    elif src not in tr.srcs or tr.type == "shahed":
                        continue  # без місця — лише ракета, яку вів цей самий канал
                    tr.closed = t
                    done += 1
                    if not places or tr.type == "shahed":
                        break  # дрон у групі — лише один, найсвіжіший
                rec["closed"] = done
            return rec
        if obs.kind == "close" and obs.type == "kab":
            n = 0
            from .config import CHANNEL_REGION
            reg = _obl_name(CHANNEL_REGION.get(src))
            regs = set(obs.avia or []) | {o for o in (obl_of(p.place) for p in places) if o}
            for z in list(self.zones):
                near = places and any(dist_km(p.place.xy, q.xy) < 40 for p in places for q in z.places)
                if near or (not places and (z.obl in regs or (not regs and (z.obl == reg or z.src == src)))):
                    self.zones.remove(z)
                    n += 1
            if obs.avia_off:
                for o in list(self.avia):
                    if o in regs or (not regs and (o == reg or reg is None)):
                        self.avia.pop(o, None)
            rec["closed"] = n
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
                    # «не фіксується» без місця стосується лише цілей, про які писав сам цей канал,
                    # і не тих, що інші канали оновили щойно (інакше один пост гасить усю область)
                    if src not in tr.srcs or (tr.last.src != src and t - tr.last.t < 180):
                        continue
                tr.closed = t
                n += 1
            rec["closed"] = n
            return rec
        if obs.kind == "avia":
            regs = list(obs.avia or [])
            regs += [o for o in (obl_of(p.place) for p in places) if o]
            if not regs:
                from .config import CHANNEL_REGION
                r = CHANNEL_REGION.get(src)
                regs = [o for o in [_obl_name(r)] if o]
            for o in dict.fromkeys(regs):
                if o not in LAUNCH_AREA:
                    continue
                a = self.avia.get(o)
                if a and t - a["t"] < AVIA_LIFE:
                    a.update(t=t, n=a["n"] + 1, act=t)
                else:
                    self.avia[o] = {"t": t, "first": t, "n": 1, "platform": None, "act": t}
                if obs.aviation:
                    self.avia[o]["platform"] = "Су-34/Су-35"
            rec["avia"] = regs
            return rec
        if obs.kind == "zone":
            if places:
                pl = [p.place for p in places]
                # та сама зона (повторна згадка) — оновлюємо час, а не плодимо дублікати
                z = next((z for z in self.zones if any(dist_km(a.xy, b.xy) < 25 for a in z.places for b in pl)), None)
                if z:
                    z.last, z.n = t, z.n + 1
                    z.ev.append({"t": int(t), "src": src, "text": (getattr(obs, "raw", "") or "")[:220], "link": link})
                    z.ev = z.ev[-8:]
                    z.places += [p for p in pl if all(dist_km(p.xy, q.xy) > 3 for q in z.places)]
                    z.places = z.places[-6:]
                else:
                    z = Zone(pl, t, src, "Су-34" if obs.aviation else None, t, 1, obl_of(pl[0]),
                             [{"t": int(t), "src": src, "text": (getattr(obs, "raw", "") or "")[:220], "link": link}])
                    self.zones.append(z)
                # КАБ летять — отже авіація в цьому напрямку активна
                if z.obl in LAUNCH_AREA:
                    a = self.avia.get(z.obl)
                    if a and t - a["t"] < AVIA_LIFE:
                        a.update(t=t, n=a["n"] + 1)
                    else:
                        self.avia[z.obl] = {"t": t, "first": t, "n": 1, "platform": None}
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
                lp = tr.last_pred
                if lp and self.brain and self.learn and 120 < t - lp[2] < 2400 and pos.place.name != (prev.place.name if prev.place else None):
                    # прогноз справдився, якщо нова фіксація в межах 20 км від передбаченого пункту
                    self.brain.pred_score(tr.type, dist_km(pt, lp[1]) <= 20)
                    tr.last_pred = None
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
            tr.course_xy = route[-1].xy if route else None
        elif pt is not None and tr.course_xy is not None:
            # нова позиція без нового пункту: старе «→ X» лишаємо, лише якщо X досі попереду
            d_c = dist_km(pt, tr.course_xy)
            if d_c < 8 or (tr.heading is not None and abs((bearing(pt, tr.course_xy) - tr.heading + 540) % 360 - 180) > 100):
                tr.course_to, tr.course_xy = None, None
        if obs.count:
            tr.count = max(tr.count or 0, obs.count) if t - tr.obs[0].t < 900 else obs.count
        rec["track"] = tr.id
        try:
            from .audit import AUDIT
            from .config import CHANNEL_REGION
            AUDIT.check(tr, obs, src, CHANNEL_REGION.get(src), oblasts().of, TYPES[tr.type]["speed"], self.brain, self.learn)
        except Exception:
            pass
        # «Чому я це показую»: що саме змінило відображення цієї цілі
        moved = bool(tr.obs and tr.obs[-1].t == t and tr.obs[-1].src == src)
        if moved and len(tr.obs) > 1 and dist_km((tr.obs[-1].x, tr.obs[-1].y), (tr.obs[-2].x, tr.obs[-2].y)) < 1.5 and tr.evidence:
            moved = False  # та сама точка — це підтвердження, а не переміщення
        why = "нова ціль" if len(tr.evidence) == 0 else ("змінило позицію" if moved else ("змінило курс" if route else "підтвердження"))
        txt = (getattr(obs, "raw", "") or "").strip()
        tr.evidence.append({"t": t, "src": src, "link": link, "text": txt[:220], "why": why, "key": _norm_key(txt),
                            "dest": route[0].name if route else None, "dxy": route[0].xy if route else None,
                            "pos": (tr.obs[-1].x, tr.obs[-1].y) if moved else None, "est": bool(moved and tr.obs[-1].est)})
        tr.evidence = tr.evidence[-40:]
        return rec

    def _best_by_target(self, typ: str, route, t: float) -> Track | None:
        """Повідомлення без позиції («курсом на X») приєднуємо до треку з тим самим пунктом призначення
        або до треку, з якого X досяжний за час, що минув."""
        if not route:
            return None
        names = {p.name for p in route}
        best, bs = None, 1e9
        for tr in self.tracks:
            if tr.type != typ or tr.closed or tr.merged or t - tr.last.t > TYPES[typ]["life"] or tr.id in self.exclude:
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
            if tr.type != typ or tr.closed or tr.merged or tr.id in self.exclude:
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

    MERGE_KM = {"jet": 30, "cruise": 35, "ballistic": 40, "geran5": 30, "banderol": 30, "shahed": 7, "molniya": 6}

    def _dedup(self, now: float) -> None:
        """Один і той самий об'єкт різні канали називають різними селами (а то й типами) — треки-близнюки зливаємо.
        Лишаємо трек із більшою кількістю незалежних джерел; дублікат ховаємо, його джерела переходять до основного."""
        act = [tr for tr in self.tracks if not tr.closed and not tr.merged and now - tr.last.t < self.life(tr)]
        pos = {tr.id: tr.est(now, SHOW_BY_TYPE.get(tr.type, SHOW_MIN)) for tr in act}

        def rank(tr):
            return (len(tr.srcs), tr.last.t)

        def same_way(a, b):
            return a.heading is None or b.heading is None or ang_diff(a.heading, b.heading) < 60

        for i, a in enumerate(act):
            if a.merged:
                continue
            for b in act[i + 1:]:
                if b.merged:
                    continue
                d = dist_km(pos[a.id], pos[b.id])
                if a.type == b.type:
                    lim = self.MERGE_KM.get(a.type, 10)
                    # шахеди летять групами — зливаємо лише «той самий пункт від різних каналів»
                    if a.type in ("shahed", "molniya") and not (a.last.label == b.last.label or d < 3):
                        continue
                elif {a.type, b.type} == {"jet", "shahed"}:
                    # «реактивний» і «шахед» в одній точці одним курсом — найчастіше той самий об'єкт, різні канали
                    lim = 8
                else:
                    continue
                if d > lim or not same_way(a, b):
                    continue
                keep, drop = (a, b) if rank(a) >= rank(b) else (b, a)
                if a.type != b.type and keep.type == "jet" and len(drop.srcs) >= len(keep.srcs):
                    keep, drop = drop, keep
                drop.merged = keep.id
                keep.srcs |= drop.srcs
                if (drop.count or 1) > (keep.count or 1) and drop.type == keep.type:
                    keep.count = drop.count
                if drop is a:
                    break

    def life(self, tr: Track) -> float:
        """Скільки ціль лишається «активною» без нових повідомлень. Долетіла до названого пункту і мовчить —
        прибираємо через 10 хв (як провідні сервіси), а не тримаємо 40 хв на місці."""
        base = TYPES[tr.type]["life"]
        fast = tr.type in FAST_TYPES
        if tr.route:
            km = sum(dist_km(a, b) for a, b in itertools.pairwise(tr.path()))
            # ракета долетіла до названого пункту і про неї мовчать — вона впала або збита: прибираємо за 3 хв
            return min(base, km / tr.speed * 3600 + (180 if fast else 600))
        if fast:
            return min(base, 300)
        return min(base, 600 if tr.last.est or tr.heading is None else 900)

    def _ev_out(self, tr: Track, now: float, here) -> dict:
        info = self.evidence(tr)
        real = [o for o in tr.obs if not o.est]
        last_real = real[-1].t if real else tr.obs[0].t
        # суперечності: різні напрямки за останні 10 хв
        vers: list[dict] = []
        for e in tr.evidence:
            if now - e["t"] > 600 or not e["dxy"]:
                continue
            b = bearing(here, e["dxy"]) if dist_km(here, e["dxy"]) > 3 else None
            if b is None:
                continue
            v = next((v for v in vers if ang_diff(v["b"], b) < 60), None)
            if v:
                v["srcs"] = sorted(set(v["srcs"]) | {e["src"]})
            else:
                vers.append({"b": round(b), "dest": e["dest"], "srcs": [e["src"]]})
        items = []
        for e in tr.evidence[-14:]:
            p = from_xy(*e["pos"]) if e["pos"] else (from_xy(*e["dxy"]) if e["dxy"] else None)
            items.append({"t": int(e["t"]), "src": e["src"], "link": e["link"], "text": e["text"], "why": e["why"], "copy": e.get("copy_of"),
                          "dest": e["dest"], "p": [round(p[1], 4), round(p[0], 4)] if p else None, "pt": "pos" if e["pos"] and not e["est"] else ("est" if e["pos"] else "dest")})
        return {"pubs": info["pubs"], "prim": info["prim"], "indep": len(info["prim"]), "items": items,
                "contra": vers if len(vers) > 1 else [], "age": int(now - last_real)}

    # ---------------- знімок стану для клієнтів
    def evidence(self, tr: Track) -> dict:
        """Групуємо публікації: однаковий текст протягом 5 хв — копія першої (перепост/ретрансляція)."""
        groups: list[dict] = []
        for e in tr.evidence:
            g = next((g for g in groups if e["key"] and g["key"] == e["key"] and e["t"] - g["t"] < 300), None)
            if g:
                g["copies"].append(e["src"])
                e["copy_of"] = g["src"]
            else:
                groups.append({"key": e["key"], "t": e["t"], "src": e["src"], "copies": []})
                e["copy_of"] = None
        prim = []
        for g in groups:
            if g["src"] not in prim:
                prim.append(g["src"])
        return {"pubs": len(tr.evidence), "prim": prim, "groups": groups}

    def conf(self, tr: Track) -> float:
        q = 1.0
        srcs = self.evidence(tr)["prim"] if tr.evidence else tr.srcs
        for s in srcs:
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
        self._dedup(now)
        for tr in self.tracks:
            if tr.merged:
                continue
            life = self.life(tr)
            age = now - tr.last.t
            status = "closed" if tr.closed else ("lost" if age > life else "active")
            if status != "active" and age > life + 900:
                continue
            ex, ey = tr.est(now, SHOW_BY_TYPE.get(tr.type, SHOW_MIN)) if status == "active" else (tr.last.x, tr.last.y)
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
                        if not tr.last_pred or tr.last_pred[0] != nx[0][0]:
                            tr.last_pred = (nx[0][0], rest[0], now)
            # навчений маршрут на 3 кроки вперед від останнього названого пункту — показ «ймовірно далі»
            lpath = []
            if status == "active" and self.brain and tr.last.place:
                la1, lo1 = from_xy(ex, ey)
                lpath = [[round(lo, 4), round(la, 4), n, p] for n, p, la, lo in self.brain.next_path(tr.type, tr.last.place.name, tr.heading, (la1, lo1))]
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
                "speed": round(tr.speed), "conf": round(conf, 2), "next": names[0] if names else tr.course_to, "route_names": names[:8], "pred": pred_src, "pred_p": pred_p, "lpath": lpath, "pos_est": tr.last.est,
                "route": [[round(from_xy(*p)[1], 4), round(from_xy(*p)[0], 4)] for p in rest[:8]],
                "trail": [[round(from_xy(o.x, o.y)[1], 4), round(from_xy(o.x, o.y)[0], 4), int(o.t)] for o in tr.obs[-6:]],
                "first": int(tr.obs[0].t), "last": int(tr.last.t), "srcs": sorted(tr.srcs),
                "links": [o.link for o in tr.obs[-5:] if o.link],
                "ev": self._ev_out(tr, now, (ex, ey)),
                "from": tr.from_place.name if tr.from_place else None, "ts": now,
                "entry": [round(from_xy(tr.obs[0].x, tr.obs[0].y)[1], 4), round(from_xy(tr.obs[0].x, tr.obs[0].y)[0], 4), tr.obs[0].label, int(tr.obs[0].t)],
                "launch": self.launches.link(tr, now, hd) if status != "closed" or age < 1800 else None,
            })
        zones = []
        self.avia = {o: a for o, a in self.avia.items() if now - a["t"] < AVIA_LIFE}

        def alive(z):
            age = now - (z.last or z.t)
            if age > KAB_MAX:
                return False
            a = self.avia.get(z.obl)
            if a and now - a.get("act", 0) < 12 * 60:   # про авіацію в цьому напрямку прямо писали щойно
                return age < KAB_AVIA
            return age < KAB_QUIET
        self.zones = [z for z in self.zones if alive(z)]
        for z in self.zones:
            age = now - (z.last or z.t)
            zones.append({"places": [[p.lon, p.lat, p.name] for p in z.places], "t": int(z.t), "last": int(z.last or z.t),
                          "n": z.n, "obl": z.obl, "platform": z.platform, "fade": round(min(1.0, age / KAB_QUIET), 2),
                          "ev": z.ev, "launch": (lambda a: {"area": LAUNCH_AREA[z.obl][2], "lat": LAUNCH_AREA[z.obl][0], "lon": LAUNCH_AREA[z.obl][1],
                                                            "avia_t": int(a["act"]) if a and a.get("act") else None} if z.obl in LAUNCH_AREA else None)(self.avia.get(z.obl)),
                          "until": int((z.last or z.t) + (KAB_AVIA if (self.avia.get(z.obl) or {}).get("act", 0) > now - 720 else KAB_QUIET))})
            for p in z.places:
                up(obl.of(p.lon, p.lat), 2)
        avia = []
        for o, a in self.avia.items():
            la, lo, area = LAUNCH_AREA[o]
            kz = [z for z in self.zones if z.obl == o]
            avia.append({"obl": o, "lat": la, "lon": lo, "area": area, "t": int(a["t"]), "first": int(a["first"]), "n": a["n"],
                         "platform": a.get("platform") or "тактична авіація", "kab": len(kz),
                         "to": [[z.places[0].lon, z.places[0].lat] for z in kz][:4],
                         "fade": round(min(1.0, (now - a["t"]) / AVIA_LIFE), 2)})
        return {"now": now, "tracks": out, "zones": zones, "avia": avia, "launches": self.launches.snapshot(now), "levels_tracker": levels, "last_update": self.last_update,
                "log": self.log[-60:]}
