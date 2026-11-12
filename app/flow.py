"""FLOW — трекер «ланцюгів і течій» (12.11, тіньовий режим; на мапу поки не виводиться).

Чим відрізняється від основного трекера (app/tracker.py):
1. Ціль — це ЛАНЦЮГ названих пунктів із фізикою: «курсом на Y» від каналу, який веде ціль, означає «зараз біля попереднього
   пункту X, іду на Y». Позиція між повідомленнями рахується рухом від «якоря» до пункту призначення з власною швидкістю
   цілі (оцінюється з інтервалів між її ж пунктами), а не стрибком у названий пункт.
2. ТЕЧІЯ ночі: хвилі йдуть тими самими коридорами. Кожен перехід X → Y, який цієї ночі вже зробила інша ціль, запам'ятовується
   (з вагою свіжості). Дійшовши до X, ланцюг продовжує рух туди, куди звідси йшли попередні; якщо таких не було — за полем
   напрямків клітинки ~25 км; якщо й поля немає — прямо.
3. Кінцеві пункти вчаться: де ланцюги зазвичай обриваються (місто-ціль), там ціль зупиняється, а не «пролітає» його.
4. Прив'язка повідомлення до цілі — за передбаченою позицією на момент повідомлення і досяжністю, з урахуванням повороту.

Усе навчання онлайн: модель знає лише те, що було до поточного повідомлення. Оцінка — scripts/flow_lab.py.
"""
from __future__ import annotations

import collections
import math
from dataclasses import dataclass, field

from .geo import ang_diff, bearing, dist_km, move

FAMILY = {"jet": "drone", "shahed": "drone", "uav": "drone", "geran5": "drone", "molniya": "near", "fpv": "near", "fpvf": "near",
          "lancet": "near", "recon": "near", "banderol": "missile", "cruise": "missile", "ballistic": "bal", "rszv": "bal"}
SPEED = {"jet": 470.0, "shahed": 170.0, "uav": 170.0, "geran5": 520.0, "molniya": 110.0, "fpv": 80.0, "fpvf": 60.0, "lancet": 95.0,
         "recon": 110.0, "banderol": 520.0, "cruise": 700.0, "ballistic": 2000.0, "rszv": 1500.0}
LIFE = {"drone": 14 * 60.0, "near": 12 * 60.0, "missile": 7 * 60.0, "bal": 3 * 60.0}
ECHO_KM = 4.0
CELL = 0.3  # клітинка поля напрямків, градуси (~25–33 км)
HALF_LIFE = 6 * 3600.0  # вага свіжості переходів: за 6 год удвічі менша


@dataclass
class Chain:
    id: int
    fam: str
    type: str
    v: float                      # км/год
    a_xy: tuple                   # якір: остання надійна позиція
    a_t: float
    dest: list = field(default_factory=list)   # черга пунктів призначення: [(name, xy)]
    hd: float | None = None       # курс у якорі
    last_t: float = 0.0
    first_t: float = 0.0
    names: list = field(default_factory=list)  # пройдені/названі пункти: [(t, name, xy, role)]
    srcs: set = field(default_factory=set)
    cont: list = field(default_factory=list)   # продовження після останнього пункту (течія): [xy]
    stop_p: float = 0.3           # імовірність, що останній пункт — кінцевий
    count: int = 1
    closed: bool = False
    v_fix: bool = False           # швидкість уже виміряна з власних пунктів


def _w(age: float) -> float:
    return 0.5 ** (max(0.0, age) / HALF_LIFE)


class FlowTracker:
    CONT = 1.0       # частка руху «течією» за останнім названим пунктом (0 — стояти в пункті)
    APPROACH_MIN = 3.0  # нова ціль «курсом на X»: за скільки хвилин до X її ставимо
    LIFE_K = 1.0

    def __init__(self, front_bearing=None):
        self.chains: list[Chain] = []
        self._id = 0
        self.trans: dict = collections.defaultdict(dict)   # (fam, name) -> {name2: [вага_t, xy2, n]}
        self.cellf: dict = collections.defaultdict(list)   # (fam, cx, cy) -> [(t, bearing, km)]
        self.ends: dict = collections.defaultdict(lambda: [0.0, 0.0])  # name -> [кінців, проходів]
        self.front_bearing = front_bearing
        self.stats = collections.Counter()

    # ---------- течія
    @staticmethod
    def _cell(xy):
        return (int(math.floor(xy[0] / 25.0)), int(math.floor(xy[1] / 25.0)))

    def _learn_leg(self, fam, a_name, a_xy, b_name, b_xy, t):
        d = dist_km(a_xy, b_xy)
        if d < 3 or d > 160:
            return
        rec = self.trans[(fam, a_name)].setdefault(b_name, [t, b_xy, 0])
        rec[0], rec[1], rec[2] = t, b_xy, rec[2] + 1
        self.cellf[(fam,) + self._cell(a_xy)].append((t, bearing(a_xy, b_xy), d))
        self.ends[a_name][1] += 1.0

    def _field(self, fam, xy, t):
        """Середній напрямок і довжина кроку в клітинці (та сусідніх), зважені свіжістю."""
        cx, cy = self._cell(xy)
        sx = sy = sw = sl = 0.0
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                k = 1.0 if (dx == 0 and dy == 0) else 0.35
                for (tt, b, d) in self.cellf.get((fam, cx + dx, cy + dy), ())[-40:]:
                    w = k * _w(t - tt)
                    sx += w * math.sin(math.radians(b)); sy += w * math.cos(math.radians(b)); sw += w; sl += w * d
        if sw < 0.8:
            return None
        r = math.hypot(sx, sy) / sw  # узгодженість 0..1
        if r < 0.45:
            return None
        return ((math.degrees(math.atan2(sx, sy)) + 360) % 360, sl / sw, r)

    def _next(self, fam, name, xy, hd_in, t):
        """Куди звідси йшли раніше: (xy, впевненість) або None."""
        best = None
        for n2, (tt, xy2, n) in self.trans.get((fam, name), {}).items():
            w = n * _w(t - tt)
            if hd_in is not None and ang_diff(hd_in, bearing(xy, xy2)) > 130 and n < 2:
                continue
            if best is None or w > best[0]:
                best = (w, xy2, n2)
        if best and best[0] >= 0.5:
            return best[1], min(0.9, 0.45 + 0.15 * best[0]), best[2]
        f = self._field(fam, xy, t)
        if f:
            b, ln, r = f
            if hd_in is None or ang_diff(hd_in, b) <= 100:
                return move(xy, b, max(12.0, min(ln, 45.0))), 0.35 * r, None
        if hd_in is not None:
            return move(xy, hd_in, 25.0), 0.2, None
        return None

    def _stop_p(self, name, pop):
        e, p = self.ends.get(name, (0.0, 0.0))
        prior = 0.75 if pop >= 250000 else (0.55 if pop >= 50000 else 0.25)
        return (e + prior * 2.0) / (e + p + 2.0)

    def _plan(self, c: Chain, t: float):
        """Продовження після останнього пункту призначення (до 3 кроків)."""
        c.cont = []
        if not c.dest:
            return
        name, xy = c.dest[-1][0], c.dest[-1][1]
        prev = c.dest[-2][1] if len(c.dest) >= 2 else c.a_xy
        hd = bearing(prev, xy) if dist_km(prev, xy) > 2 else c.hd
        c.stop_p = self._stop_p(name, c.dest[-1][2])
        for _ in range(3):
            nx = self._next(c.fam, name, xy, hd, t)
            if not nx:
                break
            xy2, conf, n2 = nx
            c.cont.append(xy2)
            if n2 is None:
                break
            hd, xy, name = bearing(xy, xy2), xy2, n2

    # ---------- кінематика
    def pos(self, c: Chain, now: float):
        d = max(0.0, c.v * (now - c.a_t) / 3600.0)
        p = c.a_xy
        for (_n, xy, _pop) in c.dest:
            seg = dist_km(p, xy)
            if d <= seg:
                return move(p, bearing(p, xy), d) if seg > 0.01 else xy
            d -= seg
            p = xy
        if c.dest:
            # за останнім названим пунктом: рух течією, ослаблений імовірністю кінцевого пункту й обмежений у часі
            d = min(d, c.v * 7.0 / 60.0) * (1.0 - c.stop_p) * self.CONT
            for xy in c.cont:
                seg = dist_km(p, xy)
                if d <= seg:
                    return move(p, bearing(p, xy), d) if seg > 0.01 else xy
                d -= seg
                p = xy
            return p
        if c.hd is None:
            return p
        return move(p, c.hd, min(d, c.v * 6.0 / 60.0) * 0.7)

    def heading(self, c: Chain, now: float):
        a, b = self.pos(c, now), self.pos(c, now + 60)
        return bearing(a, b) if dist_km(a, b) > 0.3 else c.hd

    def alive(self, c: Chain, now: float) -> bool:
        return (not c.closed) and now - c.last_t <= LIFE[c.fam] * self.LIFE_K and now >= c.first_t

    # ---------- прийом повідомлень
    def _new(self, fam, typ, t):
        self._id += 1
        c = Chain(self._id, fam, typ, SPEED.get(typ, 170.0), (0.0, 0.0), t, last_t=t, first_t=t)
        self.chains.append(c)
        return c

    def _expire(self, t):
        keep = []
        for c in self.chains:
            if c.closed or t - c.last_t > LIFE[c.fam] * self.LIFE_K + 120:
                if c.names and not c.closed:
                    self.ends[c.names[-1][1]][0] += 1.0  # ланцюг обірвався тут: кандидат у кінцеві пункти
                continue
            keep.append(c)
        self.chains = keep

    def _cost(self, c: Chain, t, typ, places, f_place):
        """Вартість приєднання повідомлення до ланцюга (км-еквівалент) або None, якщо недосяжно."""
        pc = self.pos(c, t)
        first = places[0]
        # відлуння: той самий пункт, що вже є в ланцюгу
        for (_tt, n, xy, _r) in c.names[-4:]:
            if n == first.place.name and dist_km(xy, first.place.xy) <= ECHO_KM:
                return 0.0, True
        d = dist_km(pc, first.place.xy)
        dt = max(60.0, t - c.a_t)
        if first.role == "p":
            gate = 18.0 + c.v * 4.0 / 60.0
            if d > gate and dist_km(c.a_xy, first.place.xy) > c.v * dt / 3600.0 * 1.6 + 15.0:
                return None
            if d > gate * 1.8:
                return None
            cost = d
        else:
            gate = 15.0 + c.v * 11.0 / 60.0
            if d > gate:
                return None
            cost = d * 0.6
            hd = self.heading(c, t)
            if hd is not None and d > 8:
                turn = ang_diff(hd, bearing(pc, first.place.xy))
                cost += max(0.0, turn - 50.0) * 0.35
        if f_place is not None:
            cost += min(40.0, dist_km(pc, f_place.xy)) * 0.5
        if typ != c.type and {typ, c.type} == {"jet", "shahed"}:
            cost += 25.0
        cost += min(20.0, (t - c.last_t) / 60.0)  # давно мовчить — менш імовірно та сама
        return cost, False

    def ingest(self, obs, src, t, link=None):
        fam = FAMILY.get(obs.type)
        if fam is None:
            return None
        self._expire(t)
        if obs.close or obs.safety:
            for r in obs.places:
                best = min((c for c in self.chains if c.fam == fam and self.alive(c, t)),
                           key=lambda c: dist_km(self.pos(c, t), r.place.xy), default=None)
                if best and dist_km(self.pos(best, t), r.place.xy) <= 25:
                    best.closed = True
                    self.ends[r.place.name][0] += 1.0
            return None
        if obs.kind != "track" or obs.no_target:
            return None
        places = [r for r in obs.places if r.role in ("p", "t")]
        f_place = next((r.place for r in obs.places if r.role == "f"), None)
        if not places:
            return None
        cands = []
        for c in self.chains:
            if c.fam != fam or not self.alive(c, t):
                continue
            r_ = self._cost(c, t, obs.type, places, f_place)
            if r_ is not None:
                cands.append((r_[0], r_[1], c))
        cands.sort(key=lambda x: x[0])
        if cands and cands[0][0] <= 70.0:
            _cost, echo, c = cands[0]
            self.stats["echo" if echo else "join"] += 1
        else:
            c, echo = self._new(fam, obs.type, t), False
            self.stats["new"] += 1
            first = places[0]
            if first.role == "p":
                c.a_xy = first.place.xy
            elif f_place is not None:
                c.a_xy = f_place.xy
            else:
                # лише «курсом на X»: ціль на підході; звідки — за течією клітинки, інакше від лінії фронту
                f = self._field(fam, first.place.xy, t)
                ap = f[0] if f else (self.front_bearing(first.place.xy) if self.front_bearing else None)
                c.a_xy = move(first.place.xy, (ap + 180) % 360, c.v * self.APPROACH_MIN / 60.0) if ap is not None else first.place.xy
                c.hd = ap
        c.srcs.add(src)
        c.last_t = t
        if obs.count:
            c.count = max(c.count, obs.count) if echo else obs.count
        if obs.type == "jet" and c.type in ("uav", "shahed") and not c.v_fix:
            c.type, c.v = "jet", SPEED["jet"]
        if echo:
            first = places[0]
            if first.role == "p" and c.dest and c.dest[0][0] == first.place.name:
                self._arrive(c, first.place, t)  # підтвердили «над X»: прибув у пункт призначення
            # нові пункти в тому ж повідомленні («на X, Y»: Y ще не було)
            known = {n for (_t, n, _xy, _r) in c.names}
            extra = [r for r in places[1:] if r.place.name not in known]
            if extra:
                self._extend(c, extra, t)
            return c
        pc = self.pos(c, t) if c.names else c.a_xy
        first = places[0]
        if first.role == "p":
            if c.names:
                self._measure(c, first.place.xy, t)
                self._learn_leg(fam, c.names[-1][1], c.names[-1][2], first.place.name, first.place.xy, t)
                if dist_km(c.a_xy, first.place.xy) > 3:
                    c.hd = bearing(c.a_xy, first.place.xy)
            c.a_xy, c.a_t = first.place.xy, t
            c.names.append((t, first.place.name, first.place.xy, "p"))
            # чинний пункт призначення лишається, якщо він ще попереду
            c.dest = [d for d in c.dest if d[0] != first.place.name and dist_km(first.place.xy, d[1]) > 3]
            if c.dest and c.hd is not None and ang_diff(c.hd, bearing(c.a_xy, c.dest[0][1])) > 110:
                c.dest = []
            rest = places[1:]
        else:
            if c.names:
                # «курсом на Y»: зараз біля попереднього пункту (якщо до нього вже дійшли) — це якір
                near_prev = c.dest and dist_km(pc, c.dest[0][1]) <= max(12.0, c.v * 1.5 / 60.0)
                if near_prev:
                    self._measure(c, c.dest[0][1], t)
                    pc = c.dest[0][1]
                self._learn_leg(fam, c.names[-1][1], c.names[-1][2], first.place.name, first.place.xy, t)
                c.a_xy, c.a_t = pc, t
            c.dest = []
            rest = places
        if rest:
            self._extend(c, rest, t)
        else:
            self._plan(c, t)
        return c

    def _extend(self, c: Chain, refs, t):
        prev_n, prev_xy = (c.names[-1][1], c.names[-1][2]) if c.names else (None, None)
        for i, r in enumerate(refs):
            if i > 0 and prev_n is not None:
                self._learn_leg(c.fam, prev_n, prev_xy, r.place.name, r.place.xy, t)
            c.dest.append((r.place.name, r.place.xy, getattr(r.place, "pop", 0) or 0))
            c.names.append((t, r.place.name, r.place.xy, "t"))
            prev_n, prev_xy = r.place.name, r.place.xy
        if c.dest and dist_km(c.a_xy, c.dest[0][1]) > 2:
            c.hd = bearing(c.a_xy, c.dest[0][1])
        self._plan(c, t)

    def _arrive(self, c: Chain, place, t):
        self._measure(c, place.xy, t)
        c.a_xy, c.a_t = place.xy, t
        c.dest = [d for d in c.dest if d[0] != place.name]
        self._plan(c, t)

    def _measure(self, c: Chain, xy, t):
        """Власна швидкість цілі з інтервалу між двома її пунктами."""
        d, dt = dist_km(c.a_xy, xy), t - c.a_t
        if d >= 12 and dt >= 90:
            v = d / dt * 3600.0
            nom = SPEED.get(c.type, 170.0)
            if c.type in ("uav", "shahed") and 330 <= v <= 750:
                c.type, nom = "jet", SPEED["jet"]  # «БпЛА», що йде 400+ км/год, — реактивний
            if 0.45 * nom <= v <= 1.7 * nom:
                c.v = v if not c.v_fix else 0.5 * c.v + 0.5 * v
                c.v_fix = True

    # ---------- вихід
    def shown(self, now: float):
        return [(c, self.pos(c, now)) for c in self.chains if self.alive(c, now) and c.names]


class FlowAlgo:
    """Адаптер для scripts/flow_lab.py."""
    name = "flow"

    def __init__(self):
        from .tracker import Tracker
        self.ft = FlowTracker(front_bearing=Tracker._front_bearing)

    def ingest(self, obs, src, t, link):
        return self.ft.ingest(obs, src, t, link)

    def shown(self, now, future=False):
        return [(c.fam, xy) for c, xy in self.ft.shown(now)]
