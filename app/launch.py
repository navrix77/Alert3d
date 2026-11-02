"""Ланцюжок «звідки запущено»: точки пуску / аеродроми / райони носіїв, розпізнавання повідомлень про пуски
й прив'язка кожної цілі до її пуску (повідомленого каналами — або оціненого за курсом і вивченою статистикою).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .geo import bearing, dist_km, norm, to_xy

# (назва, lat, lon, вид, типи цілей, носій/платформа, аліаси-основи укр/рос)
SITES = [
    ("Приморсько-Ахтарськ", 46.05, 38.17, "пуск", {"shahed"}, None, ["приморсько-ахтарськ", "приморско-ахтарск", "ахтарськ", "ахтарск"]),
    ("Курськ (Халіно)", 51.75, 36.30, "пуск", {"shahed", "ballistic", "jet", "cruise"}, None, ["курськ", "курск", "курщин", "халино", "халіно"]),
    ("Орел", 52.97, 36.07, "пуск", {"shahed", "jet"}, None, ["орла$", "орел$", "орёл$", "орловськ", "орловск"]),
    ("Навля", 52.83, 34.50, "пуск", {"shahed"}, None, ["навля", "навлі", "навли"]),
    ("Брянськ", 53.24, 34.36, "пуск", {"shahed", "ballistic", "jet", "cruise"}, None, ["брянськ", "брянск", "брянщин"]),
    ("Шаталово", 54.34, 32.47, "пуск", {"shahed"}, None, ["шаталов"]),
    ("Міллерово", 48.95, 40.40, "пуск", {"shahed", "jet"}, None, ["міллеров", "миллеров"]),
    ("Донецьк (аеропорт)", 48.07, 37.74, "пуск", {"shahed", "jet"}, None, ["донецьк", "донецк"]),
    ("Гвардійське (Крим)", 45.11, 33.98, "пуск", {"shahed"}, None, ["гвардійськ", "гвардейск"]),
    ("Мис Чауда (Крим)", 45.02, 35.84, "пуск", {"shahed", "ballistic"}, None, ["чауд"]),
    ("Крим", 45.30, 34.40, "пуск", {"shahed", "ballistic", "cruise", "jet"}, None, ["криму$", "крим$", "крыма$", "крым$"]),
    ("Бєлгород", 50.60, 36.60, "пуск", {"ballistic", "molniya", "jet", "shahed", "cruise"}, None, ["бєлгород", "белгород", "бєлгородщин", "белгородщин"]),
    ("Воронеж", 51.66, 39.20, "пуск", {"ballistic", "jet", "cruise"}, None, ["воронеж"]),
    ("Таганрог", 47.21, 38.94, "пуск", {"ballistic", "jet"}, None, ["таганрог"]),
    ("Ростов", 47.23, 39.72, "пуск", {"ballistic", "jet"}, None, ["ростов"]),
    ("Єйськ", 46.68, 38.27, "аеродром", {"shahed", "kab"}, None, ["єйськ", "ейск"]),
    ("Українка", 51.17, 128.45, "аеродром", {"cruise"}, "Ту-95МС", ["українк", "украинк"]),
    ("Енгельс", 51.48, 46.21, "аеродром", {"cruise"}, "Ту-95МС/Ту-160", ["енгельс", "энгельс"]),
    ("Оленья", 68.15, 33.46, "аеродром", {"cruise"}, "Ту-95МС/Ту-22М3", ["оленя", "оленья", "оленегорськ", "оленегорск"]),
    ("Шайківка", 54.23, 34.37, "аеродром", {"cruise"}, "Ту-22М3", ["шайковк", "шайківк"]),
    ("Моздок", 43.50, 44.60, "аеродром", {"cruise"}, "Ту-22М3", ["моздок"]),
    ("Район Волгодонська", 47.50, 42.00, "район пуску", {"cruise"}, "Ту-95МС", ["волгодонськ", "волгодонск"]),
    ("Каспійське море", 42.80, 48.80, "район пуску", {"cruise"}, "Ту-95МС / кораблі", ["каспі", "каспий", "каспия"]),
    ("Чорне море", 44.20, 33.40, "район пуску", {"cruise"}, "кораблі (Калібр)", ["чорного моря", "черного моря", "чорному морі", "черном море", "чорне море", "черное море"]),
    ("Азовське море", 46.30, 36.80, "район пуску", {"cruise"}, "кораблі (Калібр)", ["азовськ", "азовск"]),
    ("Морозовськ", 48.31, 41.79, "аеродром", {"kab"}, "Су-34", ["морозовськ", "морозовск"]),
    ("Бутурлинівка", 50.79, 40.60, "аеродром", {"kab"}, "Су-34/Су-35", ["бутурлинов", "бутурлинів"]),
    ("Ліпецьк", 52.70, 39.60, "аеродром", {"kab", "cruise"}, "Су-34", ["ліпецьк", "липецк"]),
]
FROM_RX = re.compile(r"(?:^|\s)(?:з|із|зі|зо|из|со|с|от|від)\s+(?:боку\s+|сторони\s+|стороны\s+|району\s+|района\s+|напрямку\s+|напрямків\s+|направления\s+|акваторії\s+|акватории\s+)?$")
LAUNCH_RX = re.compile(r"пуск|запуск|зліт|злет|взлет|взлёт|вылет|виліт|підняли|подняли|стартува|стартова|запущен|носі[їй]|носител|борт|напрямк[уів]|направлени")
CARRIER = [(re.compile(r"ту-95|ту95|ту-160|ту160"), "Ту-95МС/Ту-160", "cruise"), (re.compile(r"ту-22|ту22"), "Ту-22М3", "cruise"),
           (re.compile(r"су-34|су-35|су34"), "Су-34", "kab"), (re.compile(r"міг-31|миг-31"), "МіГ-31К", "ballistic"),
           (re.compile(r"калібр|калибр|корабл|крейсер|підводн|подводн|носі[їй] калібр"), "кораблі (Калібр)", "cruise")]
SUMMARY_RX = re.compile(r"в ніч на|у ніч на|в ночь на|протягом ночі|за ніч|за минулу добу|атакував[аи]?\s+\d|загалом")
FORECAST_RX = re.compile(r"передислокац|перебазув|перелетіл|перелетели|очікуєм|очікуєть|ожидаем|ожидает|прогноз|через \d+[-–]?\d* (?:дн|дня|днів|год)|найближчим часом")
STRIKE_RX = re.compile(r"вибух|взрыв|прил[её]т|влучан|попадан|пожеж|пожар|бавовн|хлопок")
SPEED = {"shahed": 170, "molniya": 120, "jet": 450, "cruise": 800, "ballistic": 2000, "kab": 600, "geran5": 550, "banderol": 650, "rszv": 1500, "fpv": 100, "fpvf": 80}
MAXAGE = {"shahed": 9 * 3600, "molniya": 2 * 3600, "jet": 2 * 3600, "cruise": 4 * 3600, "ballistic": 20 * 60, "kab": 30 * 60, "geran5": 3 * 3600, "banderol": 2 * 3600, "rszv": 10 * 60, "fpv": 30 * 60, "fpvf": 30 * 60}
RANGE = {"shahed": 1800, "molniya": 200, "jet": 900, "cruise": 3000, "ballistic": 600, "kab": 120, "geran5": 950, "banderol": 500, "rszv": 120, "fpv": 30, "fpvf": 40}


@dataclass
class Site:
    name: str
    lat: float
    lon: float
    kind: str
    types: set
    carrier: str | None
    xy: tuple = (0.0, 0.0)


SITE_LIST = [Site(n, la, lo, k, ty, c, to_xy(la, lo)) for n, la, lo, k, ty, c, _a in SITES]
ALIASES = sorted(((a, SITE_LIST[i]) for i, s in enumerate(SITES) for a in s[6]), key=lambda x: -len(x[0]))
BY_NAME = {s.name: s for s in SITE_LIST}


@dataclass
class Launch:
    id: str
    site: Site
    t: float
    type: str | None
    count: int | None
    carrier: str | None
    srcs: set = field(default_factory=set)
    links: list = field(default_factory=list)
    tracks: set = field(default_factory=set)
    ev: list = field(default_factory=list)  # докази: [{t, src, text, link}]


def detect(text: str, typ: str | None) -> tuple[list[Site], str | None, str | None, bool]:
    """→ (точки пуску, тип, носій, це підсумок за ніч). Порожньо, якщо повідомлення не про пуск."""
    t = norm(text)
    carrier, ctype = None, None
    for rx, name, ty in CARRIER:
        if rx.search(t):
            carrier, ctype = name, ty
            break
    launchy = bool(LAUNCH_RX.search(t)) or carrier is not None
    found: list[Site] = []
    taken: list[tuple[int, int]] = []
    for a, site in ALIASES:
        exact = a.endswith("$")
        a = a.rstrip("$")
        tail = "" if exact else (r"[а-яіїєґ']{0,6}" if len(a) >= 6 else r"[а-яіїєґ']{0,2}")
        for m in re.finditer(r"(?<![а-яіїєґa-z])" + re.escape(a) + tail + r"(?![а-яіїєґ])", t):
            s, e = m.span()
            if any(s < y and e > x for x, y in taken):
                continue
            before = t[max(0, s - 30):s]
            if not (FROM_RX.search(before) or (launchy and "напрям" in t[max(0, s - 60):s])
                    or (launchy and site.kind != "пуск") or re.search(r"(?:з|из|від|от)\s+[а-яіїє'-]+\s*$", before) and launchy):
                continue
            taken.append((s, e))
            if site not in found:
                found.append(site)
    if not found or (STRIKE_RX.search(t) and not LAUNCH_RX.search(t)) or FORECAST_RX.search(t):
        return [], None, None, False
    if ctype == "cruise" and typ in (None, "kab", "shahed"):
        typ = "cruise"
    return found, typ or ctype, carrier, bool(SUMMARY_RX.search(t))


class LaunchBook:
    """Журнал пусків і прив'язка цілей до них."""

    def __init__(self, brain=None) -> None:
        self.brain = brain
        self.items: list[Launch] = []
        self.n = 0

    def add(self, sites, typ, count, carrier, src, link, t, summary: bool, text: str | None = None) -> list[Launch]:
        if summary:  # ранковий підсумок — не живий пуск, але знання «звідки зазвичай»
            if self.brain:
                for s in sites:
                    self.brain.learn_site(typ or "shahed", s.name, None, 1.0)
            return []
        out = []
        for s in sites:
            ex = next((L for L in self.items if L.site is s and (L.type == typ or not typ or not L.type) and abs(t - L.t) < 1200), None)
            if ex:
                ex.srcs.add(src)
                ex.links = (ex.links + [link])[-6:] if link else ex.links
                ex.count = max(ex.count or 0, count or 0) or None
                ex.type = ex.type or typ
                ex.t = min(ex.t, t)
                if text:
                    ex.ev = (ex.ev + [{"t": int(t), "src": src, "text": text[:220], "link": link}])[-5:]
                out.append(ex)
                continue
            self.n += 1
            L = Launch(f"L{self.n}", s, t, typ, count, carrier or s.carrier, {src}, [link] if link else [],
                       ev=[{"t": int(t), "src": src, "text": (text or "")[:220], "link": link}] if text else [])
            self.items.append(L)
            out.append(L)
        return out

    def prune(self, now: float) -> None:
        self.items = [L for L in self.items if now - L.t < 10 * 3600]

    def link(self, tr, now: float, hd: float | None = None) -> dict | None:
        """Знайти пуск для цілі. Повертає опис ланки «пуск → вхід → ціль»."""
        first = tr.obs[0]
        p0 = (first.x, first.y)
        hd = tr.heading if hd is None else hd
        best, bs = None, 1e9
        for L in self.items:
            if L.type and L.type != tr.type and not (L.type == "shahed" and tr.type == "molniya"):
                continue
            if not L.type and tr.type not in L.site.types:
                continue
            dt = first.t - L.t
            if dt < -300 or dt > MAXAGE.get(tr.type, 3600):
                continue
            d = dist_km(L.site.xy, p0)
            fly = d / SPEED.get(tr.type, 300) * 3600  # мінімальний час дольоту до першої точки
            if dt < fly * 0.75 - 300:
                continue
            s = d / RANGE.get(tr.type, 1000) + max(0.0, dt - fly) / MAXAGE.get(tr.type, 3600) * 0.5
            if hd is not None and d > 30:
                gate = 120 if tr.type in ("shahed", "molniya") else 80
                diff = abs((bearing(L.site.xy, p0) - hd + 180) % 360 - 180)
                if diff > gate:
                    continue
                s += diff / 90
            s += 0.3 * (len(L.tracks) > 6)
            if s < bs:
                best, bs = L, s
        if best:
            best.tracks.add(tr.id)
            if self.brain and tr.type and first.place is not None and tr.id not in getattr(self, "_learned", set()):
                self._learned = getattr(self, "_learned", set()) | {tr.id}
                self.brain.learn_site(tr.type, best.site.name, first.place.name, 1.0)
            return self._out(best.site, best.t, False, best.carrier, sorted(best.srcs), best.links[-1] if best.links else None,
                             round(max(0.35, 1 - bs / 3), 2), best.id, best.count)
        return self.infer(tr, hd)

    def infer(self, tr, hd: float | None = None) -> dict | None:
        """Пуску в журналі немає: оцінка за зворотним курсом і статистикою (де такі цілі зазвичай стартують)."""
        hd = tr.heading if hd is None else hd
        if hd is None:
            return None
        first = tr.obs[0]
        p0 = (first.x, first.y)
        back = (hd + 180) % 360
        stats = self.brain.site_stats(tr.type, first.place.name if first.place else None) if self.brain else {}
        best, bs = None, 1e9
        for s in SITE_LIST:
            if tr.type not in s.types or s.kind == "аеродром" and tr.type != "kab":
                continue
            d = dist_km(s.xy, p0)
            if d < 20 or d > RANGE.get(tr.type, 1000):
                continue
            diff = abs((bearing(p0, s.xy) - back + 180) % 360 - 180)
            if diff > 35:
                continue
            sc = diff / 35 + d / RANGE.get(tr.type, 500) - math.log1p(stats.get(s.name, 0)) * 0.4
            if sc < bs:
                best, bs = s, sc
        if not best:
            return None
        p = 0.25 + 0.4 * min(1, stats.get(best.name, 0) / 10)
        return self._out(best, None, True, best.carrier, [], None, round(p, 2), None, None)

    @staticmethod
    def _out(site, t, est, carrier, srcs, link, p, lid, count) -> dict:
        return {"site": site.name, "lat": site.lat, "lon": site.lon, "kind": site.kind, "t": int(t) if t else None, "est": est,
                "carrier": carrier, "srcs": srcs, "link": link, "p": p, "id": lid, "count": count}

    def snapshot(self, now: float) -> list[dict]:
        self.prune(now)
        return [{"id": L.id, "site": L.site.name, "lat": L.site.lat, "lon": L.site.lon, "kind": L.site.kind, "t": int(L.t),
                 "type": L.type, "count": L.count, "carrier": L.carrier, "srcs": sorted(L.srcs), "links": L.links[-3:],
                 "tracks": len(L.tracks), "ev": L.ev, "site_types": sorted(L.site.types or []), "site_kind": L.site.kind} for L in self.items if now - L.t < 6 * 3600]
