"""Геодані: газетир населених пунктів, межі областей, геометрія."""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
KX = 111.32 * math.cos(math.radians(49))
KY = 110.57

OBLAST_HINTS = [
    (re.compile(r"харьковск|харківщ|харківськ"), "Харківська", (48.4, 50.5, 34.8, 38.8)),
    (re.compile(r"донецк|донеччин|донецьк"), "Донецька", (46.9, 49.3, 36.5, 39.1)),
    (re.compile(r"днепропетров|дніпропетров"), "Дніпропетровська", (47.4, 49.2, 32.6, 36.9)),
    (re.compile(r"полтав"), "Полтавська", (48.7, 50.6, 32.0, 35.6)),
    (re.compile(r"сумск|сумщин|сумськ"), "Сумська", (50.1, 52.4, 32.9, 35.8)),
    (re.compile(r"луганск|луганщ|луганськ"), "Луганська", (47.8, 50.1, 37.8, 40.3)),
    (re.compile(r"чернігів|черниг"), "Чернігівська", (50.5, 52.4, 30.4, 33.5)),
    (re.compile(r"запоріз|запорож|^\W*запоріжжя\s*:|\(запоріжжі\)"), "Запорізька", (46.6, 48.3, 34.2, 37.3)),
    (re.compile(r"київщ|киевск|київськ"), "Київська", (49.2, 51.6, 29.2, 32.2)),
]
RENAMED = {
    "первомайський": "Златопіль", "первомайский": "Златопіль", "красноград": "Берестин", "комсомольське": "Слобожанське",
    "новомосковськ": "Самар", "новомосковск": "Самар", "дніпропетровськ": "Дніпро", "днепропетровск": "Дніпро",
    "кіровоград": "Кропивницький", "кировоград": "Кропивницький", "артемівськ": "Бахмут", "артемовск": "Бахмут",
    "красноармійськ": "Покровськ", "красноармейск": "Покровськ", "димитров": "Мирноград", "орджонікідзе": "Покров",
    "комсомольськ": "Горішні Плавні", "котовськ": "Подільськ", "червоноград": "Шептицький", "червоноград": "Шептицький",
    "новоград-волинський": "Звягель", "переяслав-хмельницький": "Переяслав", "володимир-волинський": "Володимир",
    "северодонецк": "Сіверськодонецьк", "южне": "Південне", "южноукраїнськ": "Південноукраїнськ", "южноукраинск": "Південноукраїнськ",
}
REGION_WORDS = {
    "харківщина", "харківщині", "харківщину", "харківщини", "сумщина", "сумщині", "сумщину", "полтавщина",
    "полтавщині", "дніпропетровщина", "донеччина", "чернігівщина", "київщина", "черкащина",
    # історичні регіони: «загроза для … Волині та Буковини» — не села Волфине / Буковина
    "волинь", "волині", "волинню", "волынь", "волыни", "буковина", "буковини", "буковині", "буковину", "буковиной",
}
_VOW = str.maketrans({c: "" for c in "аеиіїоуюяєыэьй'ʼ’ "})


def _skel(k: str) -> str:
    """Приголосний кістяк фонетичного ключа: рос./укр. варіанти розходяться голосними (Харькова≈Харкові),
    а звичайні слова, схожі на село, — приголосними (Слідчі≠Сліди, Швидкісна≠Шведчина)."""
    return re.sub(r"(.)\1+", r"\1", k.translate(_VOW).replace("л", "в"))  # Одесса≈Одеса


_ALT = {("ц", "к"), ("з", "г"), ("с", "х"), ("г", "к")}  # Терсянці, Комишувасі; рос. Кременчуга≈Кременчук


def _skel_ok(word_key: str, place_key: str) -> bool:
    a, b = _skel(word_key), _skel(place_key)
    if a == b or a == b + "м":  # «Балабиному» — закінчення орудного/місцевого
        return True
    return len(a) == len(b) > 2 and a[:-1] == b[:-1] and (a[-1], b[-1]) in _ALT


def norm(s: str) -> str:
    return s.lower().replace("ё", "е").replace("’", "'").replace("ʼ", "'").replace("`", "'").strip()


@dataclass
class Place:
    name: str
    lat: float
    lon: float
    kind: str  # M/K/X/C або city/town/village з OSM
    pop: int = 0

    @property
    def ll(self) -> tuple[float, float]:
        return (self.lon, self.lat)

    @property
    def xy(self) -> tuple[float, float]:
        return to_xy(self.lat, self.lon)

    def as_json(self) -> dict:
        return {"n": self.name, "lat": self.lat, "lon": self.lon}


def to_xy(lat: float, lon: float) -> tuple[float, float]:
    """Локальна площина в км (центр 49°N, 31.5°E): x — схід, y — північ."""
    return ((lon - 31.5) * KX, (lat - 49) * KY)


def from_xy(x: float, y: float) -> tuple[float, float]:
    return (49 + y / KY, 31.5 + x / KX)  # lat, lon


def dist_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def bearing(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Азимут від a до b у градусах (0 — північ, за годинниковою)."""
    return (math.degrees(math.atan2(b[0] - a[0], b[1] - a[1])) + 360) % 360


def move(p: tuple[float, float], az: float, km: float) -> tuple[float, float]:
    r = math.radians(az)
    return (p[0] + math.sin(r) * km, p[1] + math.cos(r) * km)


def ang_diff(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return 360 - d if d > 180 else d


PHON = str.maketrans({"ь": "", "ъ": "", "'": "", "ё": "и", "е": "и", "є": "и", "э": "и", "и": "и", "і": "и", "ї": "и", "ы": "и", "й": "и", "ґ": "г"})


def phon(s: str) -> str:
    """Грубий фонетичний ключ, що зводить укр./рос. написання: Чугуїв≈Чугуев, Харків≈Харьков."""
    return norm(s).translate(PHON).replace("-", " ")


def lev(a: str, b: str, lim: int) -> int:
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        mn = i
        for j, cb in enumerate(b, 1):
            v = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            cur.append(v)
            mn = min(mn, v)
        if mn > lim:
            return lim + 1
        prev = cur
    return prev[-1]


class Gazetteer:
    """Індекс назв: українські (КАТОТТГ) + російські (OSM name:ru, якщо зібрано)."""

    KIND_POP = {"K": 2_000_000, "M": 50_000, "city": 200_000, "town": 20_000, "X": 4_000, "village": 800, "C": 500}

    def __init__(self) -> None:
        self.places: list[Place] = []
        self.idx: dict[str, list[int]] = {}
        self.kidx: dict[str, list[int]] = {}
        self.buckets: dict[str, list[str]] = {}

    def add(self, names: list[str], place: Place) -> None:
        i = len(self.places)
        self.places.append(place)
        for n in {norm(x) for x in names if x}:
            self.idx.setdefault(n, []).append(i)
            k = phon(n)
            if k not in self.kidx:
                self.buckets.setdefault(k[:2], []).append(k)
            self.kidx.setdefault(k, []).append(i)

    @classmethod
    @lru_cache(maxsize=1)
    def load(cls) -> "Gazetteer":
        g = cls()
        osm = DATA / "gazetteer_osm.json"
        if osm.exists():
            for e in json.loads(osm.read_text(encoding="utf-8")):
                pop = int(e.get("pop") or 0) or cls.KIND_POP.get(e.get("p", ""), 500)
                g.add([e.get("n"), e.get("uk"), e.get("ru")], Place(e.get("uk") or e.get("n"), e["lat"], e["lon"], e.get("p", ""), pop))
        for name, lat, lon, cat, _reg in json.loads((DATA / "places_katottg.json").read_text(encoding="utf-8")):
            key = norm(name)
            if key in g.idx and any(abs(g.places[i].lat - lat) < 0.02 and abs(g.places[i].lon - lon) < 0.03 for i in g.idx[key]):
                continue
            g.add([name], Place(name, lat, lon, cat, cls.KIND_POP.get(cat, 500)))
        return g

    # --- відмінки: спроба звести словоформу до називного
    @staticmethod
    def candidates(w: str) -> list[str]:
        c = [w]
        if len(w) < 4:
            return c
        b, b2, e, e2 = w[:-1], w[:-2], w[-1], w[-2:]
        if e == "у":
            c.append(b + "а")
        if e == "ю":
            c.append(b + "я")
        if e in "аеіиыу":
            c.append(b)
        if e in "иіые":
            c += [b + "а", b + "я"]
        if e not in "аеиіоуюяьй'":  # родовий множини: Черкас → Черкаси, Лубен → Лубни
            c += [w + "и", w + "і", w + "а"]
        if e2 in ("ое", "ую", "ій", "ий", "ые", "ої", "ом", "ем"):
            c += [b2 + x for x in ("ое", "ий", "е", "а", "о", "ій", "ів", "ов", "ки", "ка")]
        if e2 in ("ом", "ем"):
            c.append(b2)
        if w.endswith(("ова", "ева")):
            c.append(w[:-1])
        if w.endswith(("ові", "еві")):
            c.append(w[:-1])
        if w.endswith("ого"):
            c += [w[:-3] + "е", w[:-3] + "ий"]
        # укр. родовий/орудний від «-ів/-їв»: Богодухова, Чугуєва, Богодуховом
        # прикметник району: «Вовчанський/Вовчанського район» → Вовчанськ
        for suf in ("ський", "цький", "ського", "цького", "ському", "цькому"):
            if w.endswith(suf):
                c.append(w[: -len(suf)] + suf[:3])
                c.append(w[: -len(suf)])  # «Ізюмський район» → Ізюм, «Чугуївський» → Чугуїв
        for suf, rep in (("ова", "ів"), ("ева", "ів"), ("єва", "їв"), ("овом", "ів"), ("євом", "їв"), ("ові", "ів"), ("єві", "їв"), ("ову", "ів"), ("еву", "ів"), ("єву", "їв")):
            if w.endswith(suf):
                c.append(w[: -len(suf)] + rep)
        seen, out = set(), []
        for x in c:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out

    def lookup(self, word: str) -> list[int] | None:
        w = re.sub(r"[^а-яіїєґыэъ'\- ]", "", norm(word))
        # перейменовані міста: канали досі пишуть старі назви
        for c in self.candidates(w) if len(w) >= 4 else []:
            if c in RENAMED:
                hit = self.idx.get(norm(RENAMED[c]))
                if hit:
                    return hit
        if len(w) < 3 or w in REGION_WORDS:
            return None
        hits: list[int] = []
        for c in self.candidates(w):
            if c in self.idx:
                hits += [i for i in self.idx[c] if i not in hits]
        if hits:
            return hits
        # російська форма або дрібна розбіжність написання: фонетичний ключ + відстань редагування
        for c in self.candidates(w):
            k = phon(c)
            if k in self.kidx:
                return self.kidx[k]
        for c in self.candidates(w)[:3] if len(w) >= 6 else []:
            k = phon(c)
            lim = 1 if len(k) <= 8 else 2
            best, bd = None, lim + 1
            for kk in self.buckets.get(k[:2], ()):
                if abs(len(kk) - len(k)) > lim:
                    continue
                d = lev(k, kk, lim)
                if d < bd:
                    best, bd = kk, d
            if best and _skel_ok(k, best):
                return self.kidx[best]
        if "-" in w:
            *head, last = w.split("-")
            for c in self.candidates(last):
                k = "-".join(head) + "-" + c
                if k in self.idx:
                    return self.idx[k]
        return None

    def lookup_bigram(self, a: str, b: str) -> list[int] | None:
        A, B = norm(a), norm(b)
        for x in self.candidates(A):
            for y in self.candidates(B):
                k = f"{x} {y}"
                if k in self.idx:
                    return self.idx[k]
        return None


class Oblasts:
    """Межі областей для точка-в-полігоні."""

    def __init__(self) -> None:
        fc = json.loads((DATA / "oblasts.geojson").read_text(encoding="utf-8"))
        self.items = []
        for f in fc["features"]:
            g = f["geometry"]
            polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
            xs = [x for pl in polys for x, _ in pl[0]]
            ys = [y for pl in polys for _, y in pl[0]]
            self.items.append((f["properties"]["n"], polys, (min(xs), min(ys), max(xs), max(ys))))

    @staticmethod
    def _in_ring(ring, x, y) -> bool:
        c = False
        j = len(ring) - 1
        for i in range(len(ring)):
            xi, yi = ring[i]
            xj, yj = ring[j]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
                c = not c
            j = i
        return c

    def of(self, lon: float, lat: float) -> str | None:
        for name, polys, bb in self.items:
            if not (bb[0] <= lon <= bb[2] and bb[1] <= lat <= bb[3]):
                continue
            for pl in polys:
                if self._in_ring(pl[0], lon, lat):
                    return name
        return None


@lru_cache(maxsize=1)
def oblasts() -> Oblasts:
    return Oblasts()
