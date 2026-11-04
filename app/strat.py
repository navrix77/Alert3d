"""Стратегічна авіація (Ту-95МС, Ту-160, Ту-22М3) і МіГ-31К: групи бортів з повідомлень каналів.

Для кожної групи ведемо етап: стоїть на аеродромі → зліт → переліт/передислокація → вихід на пусковий рубіж → пуск → посадка.
Положення в повітрі рахується за часом від останнього повідомлення й крейсерською швидкістю: це ОЦІНКА (позначено est), а не
радарна позиція. Напрямки можливих ударів теж оцінка SKY за курсом і дальністю, не прогноз і не твердження каналів.
Нічого не вигадуємо: тип, кількість і місце беремо лише з тексту; якщо кількість не названа, n=None (на мапі один силует).
"""
from __future__ import annotations

import math
import re
import time

from .geo import norm
from .launch import ALIASES, BY_NAME, FORECAST_RX, PUSK_RX, REPOSITION_RX, SPECUL_RX, SUMMARY_RX, TAKEOFF_RX

# (регулярний вираз, назва, ключ значка, крейсерська швидкість км/год, дальність зброї від борту км)
FAMS = [
    (re.compile(r"ту-?95"), "Ту-95МС", "tu95", 750, 2500),
    (re.compile(r"ту-?160"), "Ту-160", "tu160", 900, 2500),
    (re.compile(r"ту-?22"), "Ту-22М3", "tu22", 850, 2200),
    (re.compile(r"міг-?31|миг-?31"), "МіГ-31К", "mig31", 1000, 2000),
]
BASE_NAMES = {"Українка", "Енгельс", "Оленья", "Шайківка", "Моздок", "Сольці", "Саваслейка"}
AREA_NAMES = {"Район Волгодонська", "Каспійське море"}
FAM_BASE = {"Ту-95МС": "tu95", "Ту-160": "tu160", "Ту-22М3": "tu22", "МіГ-31К": "mig31"}
PUSK2 = re.compile(r"(?<![а-яіїє])(?:запуск|пуск(?![а-яіїє]*(?:ов|ів))|пустил|запущ|відстріл|отстрел|стартува)")
LINE_RX = re.compile(r"рубеж|рубіж|пускових|пусковий|пусковых|вийшли на позиці|вышли на позици|у район\w* пуску|в район\w* пуска|на бойов\w+ курс")
LAND_RX = re.compile(r"посадк|(?<![а-яіїє])сіл[аи]?(?![а-яіїє])|(?<![а-яіїє])сів(?![а-яіїє])|приземл|севш|сели(?![а-яіїє])")
GROUND_RX = re.compile(r"перебува|знаходят|находят|стоять на|стоят на|на аеродромі|на аэродроме|для спорядж")
NUMW = {"один": 1, "одна": 1, "два": 2, "дві": 2, "три": 3, "чотири": 4, "п'ять": 5, "пять": 5, "шість": 6, "сім": 7, "вісім": 8, "дев'ять": 9, "десять": 10}
CITIES = [("Київ", 30.52, 50.45), ("Харків", 36.23, 49.99), ("Дніпро", 35.05, 48.46), ("Одеса", 30.72, 46.48), ("Запоріжжя", 35.14, 47.84),
          ("Львів", 24.03, 49.84), ("Миколаїв", 32.0, 46.97), ("Полтава", 34.55, 49.59), ("Вінниця", 28.47, 49.23), ("Суми", 34.8, 50.91),
          ("Житомир", 28.66, 50.25), ("Кременчук", 33.42, 49.07), ("Кривий Ріг", 33.39, 47.91), ("Івано-Франківськ", 24.71, 48.92),
          ("Рівне", 26.25, 50.62), ("Кропивницький", 32.26, 48.51), ("Чернігів", 31.29, 51.5), ("Херсон", 32.62, 46.64)]


def _km(a, b) -> float:
    """відстань між (lat, lon), км"""
    return math.hypot((a[0] - b[0]) * 111.2, (a[1] - b[1]) * 111.2 * math.cos(math.radians((a[0] + b[0]) / 2)))


def _bearing(a, b) -> float:
    """азимут з (lat, lon) у (lat, lon), градуси від півночі за годинниковою"""
    return math.degrees(math.atan2((b[1] - a[1]) * math.cos(math.radians((a[0] + b[0]) / 2)), b[0] - a[0])) % 360


def _sites(t: str) -> list[tuple[int, object]]:
    """Бази й райони стратегічної авіації, названі в тексті, у порядку появи."""
    found: list[tuple[int, object]] = []
    taken: list[tuple[int, int]] = []
    for a, site in ALIASES:
        if site.name not in BASE_NAMES and site.name not in AREA_NAMES:
            continue
        exact = a.endswith("$")
        a = a.rstrip("$")
        tail = "" if exact else (r"[а-яіїєґ'-]{0,8}" if len(a) >= 4 else r"[а-яіїєґ']{0,2}")
        for m in re.finditer(r"(?<![а-яіїєґa-z])" + re.escape(a) + tail + r"(?![а-яіїєґ])", t):
            s, e = m.span()
            if any(s < y and e > x for x, y in taken):
                continue
            taken.append((s, e))
            if all(site is not x for _, x in found):
                found.append((s, site))
    found.sort(key=lambda x: x[0])
    return found


def _count(t: str) -> int | None:
    m = re.search(r"(?<![\d.,])(\d{1,2})\s*(?:борт|літак|самол|ту-?\d|міг|миг|машин)", t) or re.search(r"\+\s*(\d{1,2})\s*борт", t)
    if m:
        return max(1, min(20, int(m.group(1))))
    m = re.search(r"(?<![а-яіїє])(один|одна|два|дві|три|чотири|п'ять|пять|шість|сім|вісім|дев'ять|десять)\s+(?:борт|літак|самол|ту-?\d|міг|миг)", t)
    return NUMW[m.group(1)] if m else None


def _missiles(t: str) -> int | None:
    m = re.search(r"(?<![\d.,])(\d{1,3})\s*(?:ракет|кр\b|х-?\d|«?калібр|«?кинджал)", t)
    return int(m.group(1)) if m else None


def parse(raw: str) -> dict | None:
    """Повідомлення → {fam, name, icon, kind, sites, n, missiles} або None, якщо це не про стратегічну авіацію."""
    t = norm(raw or "")
    if not t or SUMMARY_RX.search(t) or FORECAST_RX.search(t) or SPECUL_RX.search(t):
        return None
    fam = next((f for f in FAMS if f[0].search(t)), None)
    sites = _sites(t)
    if not fam:
        base = next((s for _, s in sites if s.name in BASE_NAMES), None)
        if not (base and re.search(r"борт", t)):
            return None
        fam = next((f for f in FAMS if f[1] in (base.carrier or "")), FAMS[0])
    if not sites and fam[2] != "mig31":
        return None
    if PUSK2.search(t):
        kind = "launch"
    elif LINE_RX.search(t):
        kind = "line"
    elif LAND_RX.search(t):
        kind = "landed"
    elif REPOSITION_RX.search(t):
        kind = "transit"
    elif TAKEOFF_RX.search(t):
        kind = "takeoff"
    elif GROUND_RX.search(t):
        kind = "ground"
    else:
        return None
    return {"fam": fam, "kind": kind, "sites": sites, "t": t, "n": _count(t), "missiles": _missiles(t)}


class StratBook:
    def __init__(self) -> None:
        self.groups: list[dict] = []
        self.n = 0

    def feed(self, raw: str, src: str, t: float, link: str | None = None) -> dict | None:
        p = parse(raw)
        if not p:
            return None
        fam, kind, sites, n = p["fam"], p["kind"], [s for _, s in p["sites"]], p["n"]
        names = [s.name for s in sites]
        # якщо у тексті кілька місць і це переліт: з першого на останнє (за порядком і «з/на»)
        origin = dest = None
        if kind == "transit" and len(sites) >= 2:
            origin, dest = names[0], names[-1]
            if re.search(r"(?:на|в напрямку)\s+" + re.escape(norm(sites[0].name))[:5], p["t"]) and not re.search(r"(?:з|із|от|от)\s+" + re.escape(norm(sites[0].name))[:5], p["t"]):
                origin, dest = names[-1], names[0]
        elif kind == "transit" and sites:
            dest = names[0]
        site = names[-1] if names else None
        g = self._find(fam[1], names, t)
        if g is None:
            self.n += 1
            g = {"id": f"S{self.n}", "name": fam[1], "icon": fam[2], "n": None, "stage": "ground", "site": None, "origin": None, "dest": None,
                 "depart": None, "t0": t, "t": t, "missiles": None, "launch_t": None, "ev": [], "srcs": [], "speed": fam[3], "range": fam[4]}
            self.groups.append(g)
        if n:
            g["n"] = n
        g["t"] = t
        g["stage"] = kind
        if kind == "transit":
            g["origin"] = origin or g["site"] or g["origin"]
            g["dest"] = dest or g["dest"]
            g["depart"] = t
            g["site"] = g["origin"] or site
        elif kind == "takeoff":
            g["origin"] = site or g["site"]
            g["site"] = site or g["site"]
            g["depart"] = t
            g["dest"] = None
        elif kind in ("landed", "ground"):
            g["site"] = site or g["dest"] or g["site"]
            g["origin"] = g["dest"] = g["depart"] = None
        elif kind in ("line", "launch"):
            g["site"] = site or g["site"]
            g["dest"] = None
            if kind == "launch":
                g["launch_t"] = t
                if p["missiles"]:
                    g["missiles"] = p["missiles"]
        g["ev"] = (g["ev"] + [{"t": int(t), "src": src, "text": (raw or "").strip()[:220], "link": link, "k": kind}])[-6:]
        if src not in g["srcs"]:
            g["srcs"].append(src)
        return g

    def _find(self, name: str, names: list[str], t: float):
        best = None
        for g in self.groups:
            if g["name"] != name or t - g["t"] > 8 * 3600:
                continue
            here = {g["site"], g["origin"], g["dest"]} - {None}
            if not names or here & set(names) or g["stage"] in ("takeoff", "transit", "line", "launch"):
                if best is None or g["t"] > best["t"]:
                    best = g
        return best

    def prune(self, now: float) -> None:
        keep = []
        for g in self.groups:
            life = {"ground": 6, "landed": 6, "takeoff": 9, "transit": 9, "line": 4, "launch": 3}.get(g["stage"], 6) * 3600
            if now - g["t"] < life:
                keep.append(g)
        self.groups = keep[-40:]

    # ---- положення й напрямки (оцінка)
    @staticmethod
    def _pt(name):
        s = BY_NAME.get(name) if name else None
        return (s.lat, s.lon) if s else None

    def _dirs(self, g, pos, hd) -> list[dict]:
        out = []
        for nm, lo, la in CITIES:
            d = _km(pos, (la, lo))
            if d > g["range"] or d < 80:
                continue
            diff = abs((_bearing(pos, (la, lo)) - hd + 180) % 360 - 180)
            if diff <= 40:
                out.append((diff + d / 200, nm, lo, la, d))
        out.sort()
        return [{"lon": lo, "lat": la, "label": nm, "km": int(d)} for _, nm, lo, la, d in out[:3]]

    def snapshot(self, now: float) -> list[dict]:
        self.prune(now)
        res = []
        for g in self.groups:
            st = g["stage"]
            base = self._pt(g["site"])
            o, d = self._pt(g["origin"]), self._pt(g["dest"])
            pos, path, trail, est = base, [], [], False
            hd = None
            if st == "transit" and o and d and g["depart"]:
                total = _km(o, d)
                f = min(1.0, max(0.0, (now - g["depart"]) / 3600 * g["speed"] / max(total, 1)))
                pos = (o[0] + (d[0] - o[0]) * f, o[1] + (d[1] - o[1]) * f)
                path, trail, est, hd = [[o[1], o[0]], [d[1], d[0]]], [[o[1], o[0]], [pos[1], pos[0]]], True, _bearing(o, d)
                if f >= 1.0:
                    st = "landed"  # розрахунково долетіли; без підтвердження каналів лишаємо як «ймовірно на місці»
            elif st == "takeoff" and base:
                est = True
            if pos is None:
                continue
            if hd is None:
                hd = _bearing(pos, (50.45, 30.52)) if st in ("takeoff", "line", "launch") else 0.0
            dirs = self._dirs(g, pos, hd) if st in ("takeoff", "transit", "line", "launch") else []
            until = g["t"] + {"ground": 6, "landed": 6, "takeoff": 9, "transit": 9, "line": 4, "launch": 3}.get(g["stage"], 6) * 3600
            res.append({"id": g["id"], "name": g["name"], "icon": g["icon"], "n": g["n"], "stage": st, "lat": pos[0], "lon": pos[1], "hd": round(hd),
                        "site": g["site"], "origin": g["origin"], "dest": g["dest"], "path": path, "trail": trail, "dirs": dirs, "t": int(g["t"]),
                        "t0": int(g["t0"]), "until": int(until), "missiles": g["missiles"], "launch_t": int(g["launch_t"]) if g["launch_t"] else None,
                        "est": est, "ev": g["ev"], "srcs": g["srcs"]})
        return res
