"""Трекер: склеює спостереження в треки цілей, рахує позицію, курс, маршрут і рівні областей."""
from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field

from .geo import Place, ang_diff, bearing, dist_km, from_xy, move, oblasts
from .geo import to_xy as _gxy
import re as _re


def _norm_key(s: str) -> str:
    """Текст без емодзі, підписів і посилань, щоб упізнати перепост."""
    s = s.lower()
    s = _re.sub(r"https?://\S+|@\w+|підпи\w*.*|подпи\w*.*", " ", s)
    s = _re.sub(r"[^а-яіїєґa-z0-9]+", " ", s).strip()
    return s[:90]

def _grams(s: str) -> frozenset:
    """Символьні трійки нормалізованого тексту (без назв каналів), для впізнавання переказу того самого посту."""
    s = s.lower()
    s = _re.sub(r"https?://\S+|@\w+|підпи\w*.*|подпи\w*.*", " ", s)
    s = _re.sub(r"[^а-яіїєґa-z0-9]+", " ", s).strip()[:200]
    return frozenset(s[i:i + 3] for i in range(len(s) - 2)) if len(s) >= 40 else frozenset()


def _same_claim(e: dict, key: str, grams: frozenset, topo: tuple, cnt) -> bool:
    """Та сама заява іншими словами: точний текст, або переказ (Жаккар трійок ≥ 0.8) з тими самими назвами й кількістю.
    Журнал 26.10–02.11: крім 4550 точних копій ще ~250 переказів («🏍 Рівненщина: реактивний БпЛА курсом на Сарни» ≈
    «Реактивний БпЛА курсом на Сарни (Рівненщина)»). Без умови назв і кількості схожість дає хибні збіги
    («Роменський район — тривога» ≈ «Ізюмський район — тривога», «2х БпЛА» ≈ «БпЛА»)."""
    if key and len(key) >= 25 and e.get("key") == key:
        return True
    g0 = e.get("g")
    if not grams or not g0 or e.get("topo") != topo or e.get("cnt") != cnt:
        return False
    return len(grams & g0) / len(grams | g0) >= 0.8


from .launch import LaunchBook
from .parser import Observation

# швидкості — з відкритих характеристик (03.11, методика «час у повітрі»): крилата 700 (Х-101 190–200 м/с),
# «Бандероль» 540 (крейсерська 520–560); шахед і реактивні — як було, їх перевіряє бектест
TYPES = {
    "shahed": {"label": "Ш", "name": "Шахед/Гербера", "speed": 170, "life": 15 * 60},  # 04.11: було 25 хв; у наліт >половини лічильника були цілі без згадок 10+ хв
    "jet": {"label": "РБ", "name": "Реактивний БпЛА", "speed": 450, "life": 15 * 60},
    "molniya": {"label": "М", "name": "«Молнія»", "speed": 120, "life": 20 * 60},
    "cruise": {"label": "КР", "name": "Крилата ракета", "speed": 700, "life": 8 * 60},
    "ballistic": {"label": "Б", "name": "Балістика", "speed": 2000, "life": 3 * 60},
    "geran5": {"label": "Г5", "name": "«Герань-5»", "speed": 550, "life": 12 * 60},
    "banderol": {"label": "БД", "name": "«Бандероль»", "speed": 540, "life": 8 * 60},
    "rszv": {"label": "РС", "name": "РСЗВ", "speed": 1500, "life": 3 * 60},
    "fpv": {"label": "FPV", "name": "FPV-дрон", "speed": 80, "life": 8 * 60},
    "fpvf": {"label": "FPV", "name": "FPV на оптоволокні", "speed": 60, "life": 8 * 60},
    "lancet": {"label": "Л", "name": "«Ланцет»", "speed": 95, "life": 20 * 60},  # 80–110 км/год, у повітрі до 30–40 хв
    "recon": {"label": "Р", "name": "Дрон-розвідник", "speed": 110, "life": 20 * 60},
}
FAST_TYPES = ("cruise", "ballistic", "banderol", "rszv", "geran5")
# КАБ: зона живе, поки про неї пишуть або поки біля кордону активна тактична авіація
KAB_QUIET = 10 * 60      # без нових згадок і без авіації — прибираємо
KAB_AVIA = 15 * 60       # авіація активна — максимум 15 хв: КАБ довше не летить, без повторних пусків загрози немає
KAB_MAX = 15 * 60        # жорстка межа від останньої згадки
AVIA_LIFE = 12 * 60      # літак на рубежі пусків — хвилини, не пів години: без нових пусків/згадок за 12 хв знімаємо
# типові райони пусків КАБ (носії Су-34/Су-35 тримаються за 40–70 км від цілі, над РФ або окупованою територією)
LAUNCH_AREA = {"Харківська": (50.62, 36.85, "Бєлгородщина"), "Сумська": (51.40, 35.35, "Курщина"),
               "Чернігівська": (52.40, 32.95, "Брянщина"), "Донецька": (48.05, 38.10, "окупована Донеччина"),
               "Луганська": (48.65, 39.35, "окупована Луганщина"), "Запорізька": (47.20, 35.95, "окупована Запорізька"),
               "Дніпропетровська": (47.45, 36.55, "окупована Запорізька"), "Херсонська": (46.50, 33.25, "лівобережжя Херсонщини"),
               "Миколаївська": (46.50, 33.25, "лівобережжя Херсонщини")}
# конкретніші райони — для зони КАБ беремо найближчий (Ізюм → Сватівський напрямок, а не Бєлгород)
LAUNCH_SPOTS = [(50.62, 36.85, "Бєлгородщина"), (51.40, 35.35, "Курщина"), (52.40, 32.95, "Брянщина"),
                (49.45, 38.15, "окупована Луганщина (Сватове)"), (48.05, 38.10, "окупована Донеччина"),
                (47.20, 35.95, "окупована Запорізька"), (46.50, 33.25, "лівобережжя Херсонщини")]


def launch_spot(p) -> tuple:
    from .geo import dist_km as _d, to_xy as _xy
    return min(LAUNCH_SPOTS, key=lambda a: _d(_xy(a[0], a[1]), p.xy))
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
    fc: tuple | None = None  # прогноз напрямку з кожного джерела в момент останньої названої позиції (журнал прогнозів)
    evidence: list = field(default_factory=list)  # [{t, src, link, text, why, dest, pos, key}]
    pred_src: str | None = None
    route_src: str | None = None  # хто назвав поточний пункт призначення (для зважування суперечливих версій)
    route_t: float = 0.0
    hd_src: str | None = None  # звідки курс: channels (названий пункт) / course (написано «курс на захід») / learned / movement
    last_pred: tuple | None = None  # (назва, xy, t, звідки xy, наївний xy) — перший крок навченого прогнозу, для самоперевірки
    pred_moved: int = 0
    pred_naive_hit: bool = False
    closed: float | None = None
    likely: bool = False  # тип — непряма ознака («ймовірно розвідник»)
    ai: bool = False  # ціль додано за розбором мовної моделі (правила її пропустили), позначка «розпізнано ШІ»
    pair: str | None = None  # канал попередив про можливу пару: «Зала (угроза ланцет)» → розвідник, pair="lancet"
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

    def est(self, now: float, cap_min: float = 4, k: float = 1.0, mapm: bool = False) -> tuple[float, float]:
        km = self.speed * k * max(0.0, now - self.last.t) / 3600
        if mapm:  # модель показу на мапі: зміщення за часом (map_disp), ліміт — зміщення за cap_min
            km = map_disp(self.type, self.speed, now - self.last.t)
            cap_km = map_disp(self.type, self.speed, cap_min * 60)
            if self.route:
                pts = self.path()
                tot = sum(dist_km(pts[i - 1], pts[i]) for i in range(1, len(pts)))
                if km <= tot or self.heading is None:
                    return along(pts, km)
                hd = bearing(pts[-2], pts[-1]) if len(pts) > 1 else self.heading
                return move(pts[-1], hd, min(km - tot, cap_km))
            if self.heading is None:
                return (self.last.x, self.last.y)
            return move((self.last.x, self.last.y), self.heading, min(km, cap_km))
        if self.route:
            pts = self.path()
            tot = sum(dist_km(pts[i - 1], pts[i]) for i in range(1, len(pts)))
            if km <= tot or self.heading is None:
                return along(pts, km)
            # пункт пройдено — летить далі тим самим курсом, доки не з'явиться нове повідомлення
            hd = bearing(pts[-2], pts[-1]) if len(pts) > 1 else self.heading
            return move(pts[-1], hd, min(km - tot, self.speed * k * cap_min / 60))
        if self.heading is None:
            return (self.last.x, self.last.y)
        # для зіставлення повідомлень — лише ~4 хв польоту; для показу на карті — довше (зона невизначеності росте)
        return move((self.last.x, self.last.y), self.heading, min(km, self.speed * k * cap_min / 60))


# Швидкість, з якою ціль «просувається» між названими каналами пунктами (для показу на мапі), — нижча за паспортну:
# повідомлення запізнюються, дрони маневрують. Бектест 26.10–02.11 (поз. похибка до наступної названої позиції,
# навчання до 01.11 09:00 / перевірка після): шахеди k≈0.3–0.4 (медіана 23.0 → 17.8 км), реактивні k≈0.6 (26.0 → 21.2 км).
# Для зіставлення повідомлень і часу підльоту лишається паспортна швидкість (обережніше).
MAP_K = {"shahed": 0.35, "jet": 0.6}
# Зміщення шахеда між названими позиціями росте повільніше за час (маневри, запізнення постів, грубі «села»):
# бектест 28.10–02.11 (n≈45 на горизонт): ≈1.0× паспортної за перші 10 хв, 0.71× за 20, 0.49× за 40.
# Модель d(h) = v·10/60·k10·(h/10)^b (h ≥ 10 хв), до 10 хв — лінійно з k10. Шахед (0.7, 0.5): медіана похибки
# через ≤10 хв 16.1 → 12.0 км (≤15 км: 47% → 60%), ≤20 хв 20.7 → 21.7, ≤40 хв 30.4 → 29.3 — проти сталого k=0.35.
# Реактивні: стале 0.6 точніше за степеневу модель — лишаємо.
MAP_POW = {"shahed": (0.7, 0.5)}


def map_disp(typ: str, speed: float, sec: float) -> float:
    """Скільки км ціль «просунулась» на мапі за sec секунд після останньої названої позиції."""
    h = max(0.0, sec) / 60
    k10, b = MAP_POW.get(typ, (MAP_K.get(typ, 1.0), 1.0))
    if h <= 10 or b == 1.0:
        return speed * h / 60 * k10
    return speed * 10 / 60 * k10 * (h / 10) ** b
SHOW_MIN = 25  # скільки хвилин ціль «летить» на карті без нового повідомлення (дрони)
# ракети летять швидко і падають/збиваються за хвилини: далі назваого пункту — лише трохи
SHOW_BY_TYPE = {"shahed": 25, "molniya": 20, "jet": 6, "cruise": 2, "ballistic": 1, "geran5": 5, "banderol": 2, "rszv": 1, "fpv": 5, "fpvf": 5, "recon": 15, "lancet": 10}


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


# «Режим балістичної загрози» (03.11): які області названо в повідомленні про балістику.
# Не положення ракети, а територія загрози, як її назвали канали; клієнт показує це для області дому.
_BAL_STEMS = [("дніпропетров", "Дніпропетровська"), ("вінниц", "Вінницька"), ("вінниччин", "Вінницька"), ("волин", "Волинська"),
              ("донец", "Донецька"), ("донеччин", "Донецька"), ("житомир", "Житомирська"), ("закарпат", "Закарпатська"),
              ("запоріз", "Запорізька"), ("франків", "Івано-Франківська"), ("київщин", "Київська"), ("київськ", "Київська"),
              ("кіровоград", "Кіровоградська"), ("луган", "Луганська"), ("львів", "Львівська"), ("миколаїв", "Миколаївська"),
              ("одес", "Одеська"), ("полтав", "Полтавська"), ("рівнен", "Рівненська"), ("сумщин", "Сумська"), ("сумськ", "Сумська"),
              ("тернопіл", "Тернопільська"), ("харків", "Харківська"), ("херсон", "Херсонська"), ("хмельниц", "Хмельницька"),
              ("хмельниччин", "Хмельницька"), ("черкас", "Черкаська"), ("черкащин", "Черкаська"), ("чернівец", "Чернівецька"),
              ("буковин", "Чернівецька"), ("чернігів", "Чернігівська")]
BAL_MACRO = [(r"східн\w*\s+(?:та\s+\w+\s+)?(?:регіон|област)|східн\w*\s+та\s+центральн|(?<![а-яіїє])на\s+сході", ["Харківська", "Донецька", "Луганська", "Дніпропетровська", "Запорізька", "Сумська"]),
             (r"центральн\w*\s+(?:та\s+\w+\s+)?(?:регіон|област)|та\s+центральн", ["Полтавська", "Черкаська", "Кіровоградська", "Київська", "Київ", "Вінницька"]),
             (r"північн\w*\s+(?:та\s+\w+\s+)?(?:регіон|област)", ["Чернігівська", "Сумська", "Київська", "Київ", "Житомирська"]),
             (r"південн\w*\s+(?:та\s+\w+\s+)?(?:регіон|област)", ["Одеська", "Миколаївська", "Херсонська", "Запорізька"])]
_BAL_OBL_RX = _re.compile(r"(?i)(?<![\w'’-])([а-яіїєґ'’-]+?(?:щин|ччин)\w*|[а-яіїєґ'’-]+?(?:ськ|цьк|зьк)(?:а|ої|ій|у)\s+обл\w*)")


# Носій «Кинджала»: зліт МіГ-31К/І — це НЕ пуск, але Повітряні сили на нього оголошують тривогу по всій Україні
# (Укрінформ, 2023–2026). Окремий етап «носій у повітрі», окремий відбій; кількість бортів ≠ кількість ракет.
MIG_RX = _re.compile(r"(?i)(?<![\w])(?:міг|миг|mig)[\s-]*31")
MIG_UP = _re.compile(r"(?i)зліт|злет|взлет|взлёт|в повітрі|у повітрі|в воздухе|підня|подня|борт|ймовірн\w*\s+застосуван|загроз\w*\s+застосуван")
MIG_DOWN = _re.compile(r"(?i)посадк|(?<![\w])сів|(?<![\w])сіли|(?<![\w])сели|приземл|відбій|отбой|без фіксац|без фиксац|імітац|имитац|повернул|вернул")


def mig_event(text: str) -> str | None:
    """'up' / 'down' / None для повідомлення про МіГ-31К/І (або «без фіксації Кинджалів»)."""
    t = text or ""
    if _re.search(r"(?i)відбій|отбой", t) and _re.search(r"(?i)(?<![\w])(?:міг|миг|mig)(?![\w])", t):
        return "down"  # «Відбій ракетної небезпеки по МІГ» (Байрактар News / Україна Головне)
    if MIG_RX.search(t) or _re.search(r"(?i)кинджал|кинжал", t):
        if MIG_DOWN.search(t):
            return "down"
        if MIG_RX.search(t) and MIG_UP.search(t) and not _re.search(r"(?i)може\s+злет|можуть\s+злет|может\s+взлет|прогноз", t):
            return "up"
    return None


def bal_oblasts(text: str) -> list[str]:
    from .parser import OBL_LIST, _obl_list
    text = OBL_LIST.sub(_obl_list, text or "")  # «загроза для Донецька, Запорізька, …» → області
    out = []
    # «загроза балістики для низки східних та центральних регіонів» (kpszsu 03.11): області не названо, лише макрорегіони.
    # Склад за поділом, яким користуються Повітряні сили у зведеннях: схід, центр, північ, південь
    low = text.lower()
    for rx, obls in BAL_MACRO:
        if _re.search(rx, low):
            out += [o for o in obls if o not in out]
    for m in _BAL_OBL_RX.finditer(text or ""):
        w = m.group(1).lower()
        for stem, o in _BAL_STEMS:
            if w.startswith(stem) and o not in out:
                out.append(o)
                break
    return out


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
    def __init__(self, sources: dict[str, Source], brain=None, learn: bool = True, audit: bool = False) -> None:
        self.speed_over: dict[str, float] = {}  # навчені швидкості (лише живий трекер; повтори доби — паспортні)
        self.audit = audit  # самоаналіз лише для живого трекера (не для повторів доби/історії)
        self.sources = sources
        self.brain = brain
        self.learn = learn
        self.tracks: list[Track] = []
        self.zones: list[Zone] = []
        self.avia: dict[str, dict] = {}  # область -> {"t", "first", "n", "platform"}
        self.counters: dict[str, int] = {}
        self.log: list[dict] = []
        self.bal: list[dict] = []
        self.ai_merge: set = set()      # пари id, які модель вважає однією ціллю (assist)
        self.merge_cands: dict = {}     # сумнівні пари для судді-моделі: frozenset(a, b) -> час  # повідомлення про балістику: які області названо (режим балістичної загрози)
        self.last_update = 0.0
        self.launches = LaunchBook(brain)
        self.exclude: set[str] = set()
        self.prefer: str | None = None

    # ---------------- стан між перезапусками
    # Без цього кожен перезапуск сервера (оновлення) обнуляв цілі, і 30 хв каналів дочитувались наново:
    # під час атаки 02–03.11 це давало стрибки лічильника (29 → 87 шахедів). Зберігаємо стан щохвилини.
    _STATE = ("tracks", "zones", "avia", "counters", "log", "last_update", "speed_over")

    def dump_state(self) -> bytes:
        import pickle
        return pickle.dumps({"v": 1, "saved": time.time(), **{k: getattr(self, k) for k in self._STATE},
                             "launches": self.launches.items, "launch_n": self.launches.n}, protocol=pickle.HIGHEST_PROTOCOL)

    def load_state(self, raw: bytes, max_age: float = 900) -> bool:
        import pickle
        from .launch import SITE_LIST
        d = pickle.loads(raw)
        if d.get("v") != 1 or time.time() - d.get("saved", 0) > max_age:
            return False
        for k in self._STATE:
            setattr(self, k, d[k])
        by_name = {s.name: s for s in SITE_LIST}
        for L in d["launches"]:  # місця пусків порівнюються за тотожністю об'єкта — повертаємо ті самі екземпляри
            L.site = by_name.get(L.site.name, L.site)
        known = {(L.site.name, L.type, int(L.t)) for L in self.launches.items}
        self.launches.items += [L for L in d["launches"] if (L.site.name, L.type, int(L.t)) not in known]
        self.launches.n = max(self.launches.n, d["launch_n"])
        self.restored_at = d["saved"]
        return True

    def _mig(self, raw: str, src: str, t: float, link: str | None) -> bool:
        m = mig_event(raw)
        if not m:
            return False
        if not any(e.get("k") == "mig" and e["src"] == src and e["txt"] == raw.strip()[:160] and t - e["t"] < 600 for e in self.bal):
            self.bal.append({"t": int(t), "src": src, "link": link, "obl": ["*"], "close": m == "down", "k": "mig",
                             "pl": [], "txt": raw.strip()[:160]})
            self.bal = [e for e in self.bal if t - e["t"] < 3600][-60:]
        return True

    def _bal_event(self, obs: Observation, src: str, t: float, link: str | None) -> None:
        from .config import CHANNEL_REGION
        raw = getattr(obs, "raw", None) or ""
        if self._mig(raw, src, t, link):
            return
        obl = bal_oblasts(raw)
        for r in obs.places:
            if r.role in ("t", "p"):
                o = obl_of(r.place)
                if o and o not in obl:
                    obl.append(o)
        if not obl:  # «Балістика!» у регіональному каналі стосується його області
            o = _obl_name(CHANNEL_REGION.get(src))
            if o:
                obl.append(o)
        self.bal.append({"t": int(t), "src": src, "link": link, "obl": obl, "close": obs.kind == "close",
                         "pl": [r.place.name for r in obs.places if r.role in ("t", "p")][:4], "txt": raw.strip()[:160]})
        self.bal = [e for e in self.bal if t - e["t"] < 3600][-60:]

    # ---------------- прийом повідомлення
    def ingest(self, obs: Observation, src: str, t: float | None = None, link: str | None = None) -> dict:
        t = t or time.time()
        self.last_update = max(self.last_update, t)
        rec = {"t": t, "src": src, "kind": obs.kind, "type": obs.type, "count": obs.count, "link": link, "track": None,
               "places": [{"r": r.role, "n": r.place.name} for r in obs.places] if not obs.safety else []}
        self.log.append(rec)
        self.log = self.log[-400:]
        try:
            if obs.type == "ballistic" and obs.kind in ("track", "info", "close", "zone"):
                self._bal_event(obs, src, t, link)
            elif getattr(obs, "raw", None):
                self._mig(obs.raw, src, t, link)
        except Exception:
            pass
        # статус тривоги («🟡 Харків та передмістя»), новина, умовний текст: місце в ньому не позиція цілі (03.11, CXID)
        if obs.no_target and not obs.close:
            return rec
        places = obs.places
        if obs.kind == "filtered":
            # «збито / вибухи / приліт» не публікуємо (безпека), але ціль після цього прибираємо з карти
            fast = FAST_TYPES if obs.type is None else ((obs.type,) if obs.type in TYPES else ())
            if fast:
                done = 0
                for tr in sorted(self.tracks, key=lambda x: -x.last.t):
                    if tr.closed or tr.merged or tr.type not in fast or t - tr.last.t > TYPES[tr.type]["life"]:
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
                if near or (not places and (z.obl in regs or (not regs and (z.obl == reg or any(e.get("src") == src for e in z.ev))))):
                    self.zones.remove(z)
                    n += 1
            if obs.avia_off:
                for o, a in list(self.avia.items()):
                    mine = any(e.get("src") == src for e in a.get("ev", []))
                    # без напрямку: регіональний канал — лише своя область; національний — лише те, про що писав сам
                    if o in regs or (not regs and (o == reg or (reg is None and mine))):
                        self.avia.pop(o, None)
            rec["closed"] = n
            return rec
        if obs.kind == "close":
            n = 0
            from .config import CHANNEL_REGION
            reg = CHANNEL_REGION.get(src)
            obl = oblasts()
            for tr in self.tracks:
                if tr.closed or tr.merged or (obs.type and tr.type != obs.type):
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
                    self.avia[o] = {"t": t, "first": t, "n": 1, "platform": None, "act": t, "ev": []}
                self.avia[o].setdefault("ev", []).append({"t": int(t), "src": src, "text": (getattr(obs, "raw", "") or "")[:220], "link": link, "k": "avia"})
                self.avia[o]["ev"] = self.avia[o]["ev"][-6:]
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
                    z = Zone(pl, t, src, "Су-34/Су-35" if getattr(obs, "su", False) else None, t, 1, obl_of(pl[0]),
                             [{"t": int(t), "src": src, "text": (getattr(obs, "raw", "") or "")[:220], "link": link}])
                    self.zones.append(z)
                # КАБ летять — отже авіація в цьому напрямку активна
                if z.obl in LAUNCH_AREA:
                    a = self.avia.get(z.obl)
                    if a and t - a["t"] < AVIA_LIFE:
                        a.update(t=t, n=a["n"] + 1)
                    else:
                        self.avia[z.obl] = {"t": t, "first": t, "n": 1, "platform": None, "ev": []}
                    self.avia[z.obl].setdefault("ev", []).append({"t": int(t), "src": src, "text": (getattr(obs, "raw", "") or "")[:220], "link": link, "k": "kab"})
                    self.avia[z.obl]["ev"] = self.avia[z.obl]["ev"][-6:]
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
            self._split_from = None
            tr = self._best_by_target(obs.type, route, t, obs.count)
            if tr and getattr(self, "_alias", None):
                route = [self._alias.get(p.name, p) for p in route]
                course_to = route[-1].name if route else None
        orig = None
        if tr:
            # «Хибна свіжість»: інший канал переслав той самий текст пізніше. Журнал 26.10–02.11: 24.5% надходжень —
            # копії, 639 із них старші за 5 хв (до 94 хв). Копія не є новим спостереженням: не скидає годинник цілі
            # (інакше позначка «замерзає» або повертається на стару точку) і не рахується незалежним підтвердженням.
            raw_ = (getattr(obs, "raw", "") or "").strip()
            key_ = _norm_key(raw_)
            g_ = _grams(raw_)
            topo_ = tuple(sorted(p.place.name for p in places))
            orig = next((e for e in tr.evidence if e["src"] != src and t - e["t"] <= 7200 and _same_claim(e, key_, g_, topo_, obs.count)), None)
            if orig is not None and t - orig["t"] > 60:
                tr.evidence.append({"t": t, "src": src, "link": link, "text": raw_[:220], "why": "перепост", "key": key_,
                                    "dest": None, "dxy": None, "pos": None, "est": False, "g": g_, "topo": topo_, "cnt": obs.count, "orig": orig["src"]})
                tr.evidence = tr.evidence[-40:]
                tr.srcs.add(src)
                rec["track"] = tr.id
                rec["copy_of"] = orig["src"]
                return rec
            if pt is not None:
                d = dist_km((tr.last.x, tr.last.y), pt)
                dt = t - tr.last.t
                nom = TYPES[tr.type]["speed"]
                if dt >= 240 and d > 2 and not tr.last.est:
                    meas = d / dt * 3600
                    if nom * 0.5 < meas < nom * 1.6:
                        tr.speed = tr.speed * 0.5 + meas * 0.5
                prev = tr.last
                if tr.last_pred and self.brain and self.learn:
                    self._score_pred(tr, pt, t)
                if self.brain and self.learn:
                    self._score_heading(tr, pt, t)
                    self._log_fc(tr, pt, t)
                    self._score_dir_claims(tr, pt, t)
                tr.obs.append(Point(t, pt[0], pt[1], src, pos.place.name, link, pos.place))
                # кінематично неможливий «перехід» (той самий пост/хвилина, сусідні села різних дронів групи,
                # >1.8× номінальної швидкості) — це не рух однієї цілі: не вчимо маршрут і не беремо з нього курс.
                # Діагностика журналу 26.10–02.11: 21% сусідніх позицій шахедів давали >300 км/год, 43% трійок — «зигзаг» >120°.
                plaus = d <= 3 or (dt >= 60 and d / dt * 3600 <= nom * 1.8)
                if self.brain and self.learn and prev.place and plaus:
                    self.brain.learn_step(tr.type, prev.place, pos.place, 0.6 if prev.est else 1.0)
                if not route and obs.course is None:
                    # Курс без названого каналами пункту. Бектест 26.10–02.11 (похибка напрямку до наступної названої
                    # позиції): «від попередньої точки» — медіана 46°, бо різні канали з різною затримкою називають
                    # сусідні села (A→B→A, 0 хв між точками); навчений «наступний пункт» — 25°. Тож: навчений, інакше рух.
                    lh = self._learned_heading(tr, pos.place, pt)
                    if lh is not None:
                        tr.heading, tr.hd_src = lh, "learned"
                    elif d > 3 and plaus and dt >= 90:
                        tr.heading, tr.hd_src = bearing((prev.x, prev.y), pt), "movement"
            elif route:
                # «на X» від каналу, що веде ціль щохвилини: ціль уже біля X (так показують провідні сервіси).
                # Переносимо її в X, якщо X досяжний за час від останньої фіксації; курс — звідки прийшла.
                X = route[0]
                e = tr.est(t)
                reach = tr.speed * max(60.0, t - tr.last.t) / 3600 * 1.6 + 12
                # і не швидше за 2.5× номінальної від останньої фіксації: «курсом на X» щохвилини від кількох каналів
                # інакше «стрибає» ціль на 25–40 км за пів хвилини (аудит: Васильків→Борщагівка 2195 км/год)
                jump = dist_km((tr.last.x, tr.last.y), X.xy) <= TYPES[tr.type]["speed"] * 2.5 * max(30.0, t - tr.last.t) / 3600 + 5
                if dist_km(e, X.xy) <= reach and jump:
                    prev = tr.last
                    tr.obs.append(Point(t, X.xy[0], X.xy[1], src, X.name, link, X, True))
                    if dist_km((prev.x, prev.y), X.xy) > 3:
                        tr.heading = bearing((prev.x, prev.y), X.xy)
                    route = route[1:]
                    if not route:
                        # ціль уже в X (оцінка) і нового пункту не названо: «→ X» більше не показуємо,
                        # а куди вона далі — невідомо (02.11: «→ Циркуни» на шахеді, що «полетів» до Богодухова)
                        course_to, tr.course_to, tr.course_xy = None, None, None
            if route:
                # пункт, до якого понад годину польоту, — це тезка з іншого кінця країни, не маршрут цієї цілі
                here = tr.est(t)
                route = [p for p in route if dist_km(here, p.xy) <= min(tr.speed * 1.0 + 60, 260 if tr.type == "shahed" else 900)]
                if len(route) >= 2:
                    # «курсом на Лозова/Питомник» над Лісним (04.11): варіанти через «/» — сусідні пункти; пункт, що набагато
                    # далі за найближчий і відірваний від решти маршруту на 80+ км, — тезка (Лозова на півдні), а не курс:
                    # інакше оцінка «летить» через центр Харкова
                    dmin = min(dist_km(here, p.xy) for p in route)
                    keep = []
                    for p in route:
                        far = dist_km(here, p.xy) > 3 * dmin + 60
                        lone = all(dist_km(p.xy, q.xy) > 80 for q in route if q is not p)
                        if not (far and lone):
                            keep.append(p)
                    if keep and len(keep) < len(route):
                        rec["dropped_far"] = [p.name for p in route if p not in keep]
                        route = keep
                        course_to = route[-1].name
                if not route:
                    course_to = None  # усі пункти — тезки з іншого кінця країни: «→ X» не показуємо
            if route and tr.route and tr.route_src and tr.route_src != src and t - tr.route_t < 600 and self.brain and hasattr(self.brain, "dir_rel"):
                # дві версії курсу від різних каналів за 10 хв: якщо попередній канал доведено точніший у напрямках
                # (апостеріорна частка ≥ на 0.15 вища, ≥15 перевірених заяв) — лишаємо його версію; нова йде в докази як «інша версія»
                here_ = (tr.last.x, tr.last.y)
                if ang_diff(bearing(here_, tr.route[0].xy), bearing(here_, route[0].xy)) > 60:
                    a_old, n_old = self.brain.dir_rel(tr.route_src)
                    a_new, _n_new = self.brain.dir_rel(src)
                    if n_old >= 15 and a_old - a_new >= 0.15:
                        route, course_to = [], tr.course_to
                        rec["kept_version"] = tr.route_src
            if route:
                # ціль змінила пункт призначення: послідовність «курсом на A» → «курсом на B» теж маршрут
                old = tr.route[0] if tr.route else None
                if self.brain and self.learn and old and old.name not in names:
                    self.brain.learn_step(tr.type, old, route[0], 0.7)
                tr.route = route
                tr.route_src, tr.route_t = src, t
            elif pt is not None:
                tr.route = [p for p in tr.route if dist_km(p.xy, pt) > 3]
            tr.route = [p for p in tr.route if dist_km(p.xy, (tr.last.x, tr.last.y)) > 1.5]
            if tr.route:
                tr.heading, tr.hd_src = bearing((tr.last.x, tr.last.y), tr.route[0].xy), "channels"
            elif obs.course is not None:
                tr.heading, tr.hd_src = obs.course, "course"
        else:
            c = self.counters[obs.type] = self.counters.get(obs.type, 0) + 1
            tr = Track(f"{TYPES[obs.type]['label']}-{c}", obs.type, self.speed_over.get(obs.type, TYPES[obs.type]["speed"]))
            grp = getattr(self, "_split_from", None)
            if grp is not None and pos is None and (grp.count or 1) >= 2:
                grp.count -= 1  # відділився від групи: у групі на одного менше
                self._split_from = None
            tr.likely = bool(getattr(obs, "likely", False))
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
                tr.route_src, tr.route_t = src, t
            if tr.route:
                tr.heading, tr.hd_src = bearing((tr.last.x, tr.last.y), tr.route[0].xy), "channels"
            elif obs.course is not None:
                tr.heading, tr.hd_src = obs.course, "course"
            elif frm and pos is not None and dist_km(frm.place.xy, pt) > 3:
                tr.heading, tr.hd_src = bearing(frm.place.xy, pt), "from"
            elif pos is not None:
                lh = self._learned_heading(tr, pos.place, pt)  # нова ціль без курсу: навчений напрямок із цього пункту
                if lh is not None:
                    tr.heading, tr.hd_src = lh, "learned"
            tr.from_place = frm.place if frm else None
            self.tracks.append(tr)
        # канал прямо назвав «звідки → куди»: це теж знання про маршрут
        if self.brain and self.learn and real is not None and route:
            self.brain.learn_step(obs.type, real.place, route[0], 0.5)
        # довіра: друге незалежне джерело підтверджує всіх, хто вже повідомив про цю ціль
        # копія/переказ навіть у першу хвилину — не незалежне підтвердження (методика: подвійний рахунок)
        if src not in tr.srcs and tr.srcs and self.brain and self.learn and orig is None:
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
        if getattr(obs, "pair", None):
            tr.pair = obs.pair
        if getattr(obs, "ai", False) and len(tr.obs) <= 1:
            tr.ai = True
        elif not getattr(obs, "ai", False):
            tr.ai = False  # правила підтвердили — це вже не лише оцінка моделі
        if obs.count:
            tr.count = max(tr.count or 0, obs.count) if t - tr.obs[0].t < 900 else obs.count
        rec["track"] = tr.id
        if self.audit:
            try:
                from .audit import AUDIT
                from .config import CHANNEL_REGION
                AUDIT.check(tr, obs, src, CHANNEL_REGION.get(src), oblasts().of, TYPES[tr.type]["speed"], self.brain, self.learn, t)
            except Exception:
                pass
        # «Чому я це показую»: що саме змінило відображення цієї цілі
        moved = bool(tr.obs and tr.obs[-1].t == t and tr.obs[-1].src == src)
        if moved and len(tr.obs) > 1 and dist_km((tr.obs[-1].x, tr.obs[-1].y), (tr.obs[-2].x, tr.obs[-2].y)) < 1.5 and tr.evidence:
            moved = False  # та сама точка — це підтвердження, а не переміщення
        why = "нова ціль" if len(tr.evidence) == 0 else ("змінило позицію" if moved else ("змінило курс" if route else "підтвердження"))
        txt = (getattr(obs, "raw", "") or "").strip()
        tr.evidence.append({"t": t, "src": src, "link": link, "text": txt[:220], "why": why, "key": _norm_key(txt),
                            "g": _grams(txt), "topo": tuple(sorted(p.place.name for p in places)), "cnt": obs.count,
                            "orig": orig["src"] if orig is not None else None,
                            "dest": route[0].name if route else None, "dxy": route[0].xy if route else None,
                            "pos": (tr.obs[-1].x, tr.obs[-1].y) if moved else None, "est": bool(moved and tr.obs[-1].est)})
        tr.evidence = tr.evidence[-40:]
        if self.brain and self.learn:
            self._open_fc(tr, src, t)
        return rec

    def _log_fc(self, tr: Track, pt, t: float) -> None:
        """Закрити прогноз попередньої названої позиції: куди ціль назвали далі (>5 км, через 3–40 хв)."""
        if not tr.fc or not hasattr(self.brain, "log_fc"):
            return
        t0, x0, y0, src0, cand = tr.fc
        d = dist_km((x0, y0), pt)
        if 180 <= t - t0 <= 2400 and d > 5:
            self.brain.log_fc(t0, tr.type, src0, cand, round(bearing((x0, y0), pt), 1), round(t - t0), round(d, 1))
            tr.fc = None
        elif t - t0 > 2400:
            tr.fc = None

    def _open_fc(self, tr: Track, src: str, t: float) -> None:
        """Записати, що кожне джерело пропонує як напрямок зараз (канали / навчений маршрут / рух / показаний)."""
        o = tr.last
        if o.est or o.t != t:
            return
        P, c = (o.x, o.y), {}
        if tr.route and dist_km(P, tr.route[0].xy) > 3:
            c["ch"] = round(bearing(P, tr.route[0].xy), 1)
        if o.place is not None and self.brain and hasattr(self.brain, "next_path"):
            la, lo = from_xy(*P)
            nx = self.brain.next_path(tr.type, o.place.name, tr.heading, (la, lo), steps=1)
            if nx:
                q = _gxy(nx[0][2], nx[0][3])
                if dist_km(P, q) > 3:
                    c["ln"], c["lnp"] = round(bearing(P, q), 1), round(nx[0][1], 2)
        real = [x for x in tr.obs[:-1] if not x.est]
        if real:
            pv = real[-1]
            d, dt = dist_km((pv.x, pv.y), P), t - pv.t
            if d > 3 and dt >= 90 and d / dt * 3600 <= TYPES[tr.type]["speed"] * 1.8:
                c["mv"] = round(bearing((pv.x, pv.y), P), 1)
        if tr.heading is not None:
            c["cur"] = round(tr.heading, 1)
        if c:
            tr.fc = (t, P[0], P[1], src, c)
        # злиття джерел напрямку — лише коли журнал прогнозів довів виграш (app/fusion.py, рішення раз на добу)
        fz = getattr(self, "fusion", None)
        if fz and fz.get("on") and sum(k in c for k in ("ch", "ln", "mv")) >= 2:
            from .fusion import fuse
            f = fuse(c, fz.get("kappa") or {}, tr.type)
            if f is not None:
                tr.heading, tr.hd_src = f, "fused"

    def _score_heading(self, tr: Track, pt, t: float) -> None:
        """Жива самоперевірка напрямку: курс, який показувала мапа після останньої НАЗВАНОЇ позиції, проти того,
        куди ціль насправді назвали далі (>5 км, через 3–40 хв). Влучання, ≤45°."""
        real = next((o for o in reversed(tr.obs) if not o.est), None)
        if real is None or not 180 <= t - real.t <= 2400:
            return
        a = (real.x, real.y)
        if dist_km(a, pt) <= 5:
            return
        shown = bearing(a, tr.route[0].xy) if tr.route and dist_km(a, tr.route[0].xy) > 3 else tr.heading
        if shown is None:
            return
        self.brain.pred_score(tr.type + "@hd", ang_diff(shown, bearing(a, pt)) <= 45)

    def _score_dir_claims(self, tr: Track, pt, t: float) -> None:
        """Точність напрямку кожного каналу: «курсом на X», чи ціль потім (3–40 хв) справді рушила в бік X (≤30°).
        Журнал 26.10–02.11: у середньому 67% (n=184), між каналами 50–93%, але вибірки по 5–28 заяв,
        тож вагу каналу беремо лише з апостеріорної оцінки й лише за ≥15 перевірених заяв."""
        if not hasattr(self.brain, "pred_score"):
            return
        real = [o for o in tr.obs if not o.est]
        for e in tr.evidence:
            if e.get("sc") or not e.get("dxy") or not 180 <= t - e["t"] <= 2400:
                continue
            before = [o for o in real if o.t <= e["t"]]
            if not before:
                continue
            p0 = (before[-1].x, before[-1].y)
            if dist_km(p0, e["dxy"]) < 10 or dist_km(p0, pt) <= 8:
                continue
            e["sc"] = 1
            self.brain.pred_score("dir:" + e["src"], ang_diff(bearing(p0, pt), bearing(p0, e["dxy"])) <= 30)

    def _learned_heading(self, tr: Track, place, pt) -> float | None:
        if not self.brain or not place or not hasattr(self.brain, "next_places"):
            return None
        la, lo = from_xy(*pt)
        nx = self.brain.next_places(tr.type, place.name, None, (la, lo))
        if nx and nx[0][1] >= 0.3:
            xy = _gxy(nx[0][2], nx[0][3])
            if 3 < dist_km(pt, xy) <= 110:  # навчений «наступний пункт» за 100+ км — помилка навчання, не курс
                return bearing(pt, xy)
        return None

    def _score_pred(self, tr: Track, pt, t: float) -> None:
        """Чесна самоперевірка навченого прогнозу «ймовірно далі X» (бектест 26.10–02.11 показав, що стара
        метрика, «наступна фіксація ≤20 км від X», карала прогноз за кожне підтвердження поточного місця).
        Влучання: ціль названо ≤15 км від X протягом 40 хв. Промах: за 40 хв ціль названо деінде (>5 км від
        місця прогнозу), але не біля X. Невідомо (ціль зникла), не рахується. Поруч, наївний базовий прогноз
        «30 км тим самим курсом», щоб було видно, чи навчання взагалі краще за просту екстраполяцію."""
        name, xy, t0, origin, naive = tr.last_pred
        if pt is not None and t - t0 <= 2400:
            if naive is not None and dist_km(pt, naive) <= 15:
                tr.pred_naive_hit = True
            if dist_km(pt, xy) <= 15:
                self.brain.pred_score(tr.type + "@2", True)
                if naive is not None:
                    self.brain.pred_score(tr.type + "@2:naive", tr.pred_naive_hit)
                tr.last_pred, tr.pred_moved, tr.pred_naive_hit = None, 0, False
                return
            if dist_km(pt, origin) > 5 and (not tr.obs or dist_km(pt, (tr.obs[-1].x, tr.obs[-1].y)) > 5):
                tr.pred_moved += 1  # нове, інше місце — не біля X
        if tr.pred_moved >= 2 or (t - t0 > 2400 and tr.pred_moved):  # двічі назвали деінде або минуло 40 хв
            self.brain.pred_score(tr.type + "@2", False)
            if naive is not None:
                self.brain.pred_score(tr.type + "@2:naive", tr.pred_naive_hit)
            tr.last_pred, tr.pred_moved, tr.pred_naive_hit = None, 0, False
        elif t - t0 > 2400:
            tr.last_pred, tr.pred_moved, tr.pred_naive_hit = None, 0, False  # ціль зникла — невідомо, не рахуємо

    def _best_by_target(self, typ: str, route, t: float, count: int | None = None) -> Track | None:
        """Повідомлення без позиції («курсом на X») приєднуємо до треку з тим самим пунктом призначення
        або до треку, з якого X досяжний за час, що минув."""
        if not route:
            return None
        best, bs = None, 1e9
        alias, alias_t = None, 0.0
        self._alias = {}
        for tr in self.tracks:
            if tr.type != typ or tr.closed or tr.merged or t - tr.last.t > TYPES[typ]["life"] or tr.id in self.exclude:
                continue
            # «той самий пункт» — за координатами, а не лише за назвою: Затока під Чугуєвом ≠ Затока на Одещині
            tpl = list(tr.route) + ([type("P", (), {"name": tr.course_to, "xy": tr.course_xy})] if tr.course_to and tr.course_xy else [])
            shared = {p.name for p in route if any(q.name == p.name and dist_km(p.xy, q.xy) < 10 for q in tpl)}
            known = [q for q in list(tr.route) + [getattr(tr.last, "place", None)] if q is not None]
            namesake = [(p, q) for p in route for q in known if q.name == p.name and dist_km(p.xy, q.xy) >= 10]
            e = tr.est(t)
            d = min(dist_km(e, p.xy) for p in route)
            if namesake and not shared and tr.last.t > alias_t and t - tr.last.t < 1200:
                alias, alias_t = (tr, namesake), tr.last.t
            if tr.id == self.prefer and d < 80:
                return tr  # канал прямо пише «далі …» про ту саму ціль
            # «1 ударний курсом на Вільшани» не перенацілює всю групу «4 ударних на Шевченкове»: від групи відділився
            # один дрон (03.11, monitor 1654 / Харьков INFO: «Шахед ×4 → Вільшани»)
            if not shared and count == 1 and (tr.count or 1) >= 2 and tr.id != self.prefer:
                if d <= 35:
                    self._split_from = tr
                continue
            if not shared:
                # нова ціль-пункт має бути попереду (за курсом) і досяжна приблизно за 15 хв
                if d > min(35, tr.speed * 0.25 + 15):
                    continue
                if tr.heading is not None and not tr.last.est and d > 8 and ang_diff(tr.heading, bearing(e, route[0].xy)) > 75:
                    continue
            s = d - (40 if shared else 0)
            if s < bs:
                best, bs = tr, s
        if best is None and alias:
            # національний канал назвав тезку («на Затоку»), а ціль такого типу вже летить на одноіменний пункт
            # в іншому кінці країни — це та сама ціль; беремо її пункт, а не село-тезку
            tr, pairs = alias
            self._alias = {p.name: q for p, q in pairs}
            return tr
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
        """Один і той самий об'єкт різні канали називають різними селами (а то й типами), треки-близнюки зливаємо.
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
                ai_same = frozenset((a.id, b.id)) in self.ai_merge
                near_cand = d <= 25 and (a.type == b.type or {a.type, b.type} <= {"jet", "shahed", "recon", "molniya"})
                if a.type == b.type:
                    lim = self.MERGE_KM.get(a.type, 10)
                    # шахеди летять групами — зливаємо лише «той самий пункт від різних каналів»
                    # або сильний збіг (04.11, дублі в наліт): різні канали назвали сусідні пункти (≤12 км) майже одночасно
                    # (≤6 хв), і в обох той самий названий пункт призначення/курс або близький напрямок (<30°).
                    # Групи (у обох count>1) і повідомлення одного й того ж каналу не склеюємо — це справді різні
                    if a.type in ("shahed", "molniya") and not (a.last.label == b.last.label or d < 3) and not ai_same:
                        strong = (d <= 12 and abs(a.last.t - b.last.t) <= 360 and not (a.srcs & b.srcs)
                                  and not ((a.count or 1) > 1 and (b.count or 1) > 1)
                                  and ((a.course_to and a.course_to == b.course_to)
                                       or (a.heading is not None and b.heading is not None and ang_diff(a.heading, b.heading) < 30)))
                        if not strong:
                            if near_cand:
                                self.merge_cands.setdefault(frozenset((a.id, b.id)), now)
                            continue
                elif {a.type, b.type} == {"jet", "shahed"}:
                    # «реактивний» і «шахед» в одній точці одним курсом — найчастіше той самий об'єкт, різні канали
                    lim = 8
                elif ai_same:
                    lim = 12
                else:
                    if near_cand:
                        self.merge_cands.setdefault(frozenset((a.id, b.id)), now)
                    continue
                # той самий пункт призначення («на П'ятихатки» від двох каналів) — курс із «центру міста» міг бути хибним (03.11)
                dest = lambda tr: ({p.name for p in tr.route} | ({tr.course_to} if tr.course_to else set()))
                ok = d <= lim and (same_way(a, b) or (a.type != b.type and dest(a) & dest(b)))
                if not ok and frozenset((a.id, b.id)) in self.ai_merge and d <= max(lim, 12) * 2:
                    ok = True  # модель упевнено сказала «та сама ціль», і вони поруч
                if not ok:
                    if near_cand:
                        self.merge_cands.setdefault(frozenset((a.id, b.id)), now)
                    continue
                # той самий канал майже одночасно написав про дві цілі («шахед на Чугуїв» + «ще шахед на Чугуїв») — це різні
                if a.srcs & b.srcs and abs(a.obs[0].t - b.obs[0].t) < 120:
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
        """Скільки ціль лишається «активною» без нових повідомлень. Долетіла до названого пункту і мовчить,
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

    def track_evidence(self, tid: str, now: float | None = None) -> dict | None:
        """Повні докази однієї цілі, за запитом (панель цілі / рентген), а не в кожному знімку для всіх."""
        now = now or time.time()
        tr = next((t for t in self.tracks if t.id == tid), None)
        if tr is None:
            return None
        return self._ev_out(tr, now, tr.est(now))

    # ---------------- знімок стану для клієнтів
    def evidence(self, tr: Track) -> dict:
        """Групуємо публікації: однаковий текст протягом 5 хв, копія першої (перепост/ретрансляція)."""
        groups: list[dict] = []
        for e in tr.evidence:
            g = next((g for g in groups if (e.get("orig") == g["src"] and e["t"] - g["t"] < 7200)
                      or (e["key"] and g["key"] == e["key"] and e["t"] - g["t"] < 300)), None)
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

    def quality(self, tr: Track, now: float, conf: float | None = None) -> dict:
        """Дві різні речі замість одного «conf» (04.11, незалежна оцінка):
        впізнання — наскільки певно, що така ціль справді є (джерела, їхня надійність);
        місце — наскільки точно відомо, де вона зараз (остання названа точка + час, що минув, і швидкість)."""
        conf = self.conf(tr) if conf is None else conf
        n_ind = len(self.evidence(tr)["prim"]) if tr.evidence else len(tr.srcs)
        id_lvl = "висока" if conf >= 0.85 and n_ind >= 2 else "середня" if conf >= 0.5 else "низька"
        fixes = [o for o in tr.obs if not o.est]
        if not fixes:
            return {"id_conf": round(conf, 2), "id_lvl": id_lvl, "n_indep": n_ind, "pos_km": None, "pos_lvl": "невідоме", "fix_age": None}
        f = fixes[-1]
        pop = getattr(f.place, "pop", 0) or 0
        base = 2 if getattr(f.place, "kind", "") == "D" else 8 if pop >= 100_000 else 4  # район міста / велике місто / селище
        age = max(0.0, (now - f.t) / 60)
        # журнал: похибка оцінки ≈15–20 км через 10 хв і ≈30 км через 20 хв для шахедів; швидші цілі — пропорційно
        km = base + 1.6 * min(age, 90) * max(1.0, tr.speed / 170) ** 0.5
        km = min(round(km), 200)
        lvl = "точне" if km <= 8 else "приблизне" if km <= 30 else "грубе"
        return {"id_conf": round(conf, 2), "id_lvl": id_lvl, "n_indep": n_ind, "pos_km": km, "pos_lvl": lvl, "fix_age": int(now - f.t)}

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
            if tr.last_pred and self.brain and self.learn and now - tr.last_pred[2] > 2400:
                self._score_pred(tr, None, now)
            life = self.life(tr)
            age = now - tr.last.t
            status = "closed" if tr.closed else ("lost" if age > life else "active")
            if status != "active" and age > life + 900:
                continue
            mk = MAP_K.get(tr.type, 1.0)
            ex, ey = tr.est(now, SHOW_BY_TYPE.get(tr.type, SHOW_MIN), mk, mapm=True) if status == "active" else (tr.last.x, tr.last.y)
            lat, lon = from_xy(ex, ey)
            km = map_disp(tr.type, tr.speed, min(age, life))
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
            pred_next = None
            if not rest and status == "active" and self.brain:
                base = tr.last.place.name if tr.last.place else None
                if base:
                    la0, lo0 = from_xy(ex, ey)
                    nx = self.brain.next_places(tr.type, base, tr.heading, (la0, lo0))
                    if nx and nx[0][1] >= 0.3:
                        # навчений прогноз — НЕ курс: у «next» (підпис «→ X» на мапі) лише те, що написали канали.
                        # Прогноз іде окремо (pred_next / lpath) і показується лише в картці цілі як «ймовірно далі».
                        pred_src, pred_p = "learned", round(nx[0][1], 2)
                        pred_next = nx[0][0]
                        if not tr.last_pred or tr.last_pred[0] != nx[0][0]:
                            from .geo import to_xy
                            o_ = (tr.last.x, tr.last.y)
                            naive = move(o_, tr.heading, 30) if tr.heading is not None else None
                            tr.last_pred = (nx[0][0], to_xy(nx[0][2], nx[0][3]), now, o_, naive)
                            tr.pred_moved, tr.pred_naive_hit = 0, False
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
                "id": tr.id, "type": tr.type, "name": TYPES[tr.type]["name"] + (" (ймовірно)" if tr.likely else ""), "likely": tr.likely, "pair": tr.pair, "ai": tr.ai, "count": tr.count, "status": status,
                "lat": round(lat, 5), "lon": round(lon, 5), "hd": None if hd is None else round(hd, 1),
                **self.quality(tr, now, conf),
                "speed": round(tr.speed), "conf": round(conf, 2), "next": names[0] if names else tr.course_to, "route_names": names[:8], "vmap": round(tr.speed * MAP_K.get(tr.type, 1.0)), "dm": list(MAP_POW.get(tr.type, (MAP_K.get(tr.type, 1.0), 1.0))), "pred": pred_src, "pred_p": pred_p, "hd_src": "channels" if rest else tr.hd_src, "pred_next": pred_next, "lpath": lpath, "pos_est": tr.last.est, "nopos": all(o.est for o in tr.obs),
                "route": [[round(from_xy(*p)[1], 4), round(from_xy(*p)[0], 4)] for p in rest[:8]],
                "trail": [[round(from_xy(o.x, o.y)[1], 4), round(from_xy(o.x, o.y)[0], 4), int(o.t)] for o in tr.obs[-6:]],
                "first": int(tr.obs[0].t), "last": int(tr.last.t), "srcs": sorted(tr.srcs),
                "links": [o.link for o in tr.obs[-5:] if o.link],
                "ev": {k: v for k, v in self._ev_out(tr, now, (ex, ey)).items() if k != "items"},  # докази — /api/track/{id}
                "from": tr.from_place.name if tr.from_place else None, "ts": now,
                "entry": [round(from_xy(tr.obs[0].x, tr.obs[0].y)[1], 4), round(from_xy(tr.obs[0].x, tr.obs[0].y)[0], 4), tr.obs[0].label, int(tr.obs[0].t)],
                # останній пункт, який назвали самі канали (не оцінка SKY): «де ціль зараз» у картці
                "at": next(([o.label, int(o.t)] for o in reversed(tr.obs) if not o.est and o.label), None),
                "at_ll": next(([round(from_xy(o.x, o.y)[1], 4), round(from_xy(o.x, o.y)[0], 4)] for o in reversed(tr.obs) if not o.est), None),
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
                          "ev": z.ev, "launch": (lambda a, sp: {"area": sp[2], "lat": sp[0], "lon": sp[1],
                                                                "avia_t": int(a["act"]) if a and a.get("act") else None})(self.avia.get(z.obl), launch_spot(z.places[0])),
                          "until": int((z.last or z.t) + (KAB_AVIA if (self.avia.get(z.obl) or {}).get("act", 0) > now - 720 else KAB_QUIET))})
            for p in z.places:
                up(obl.of(p.lon, p.lat), 2)
        avia = []
        for o, a in self.avia.items():
            kz = [z for z in self.zones if z.obl == o]
            la, lo, area = launch_spot(kz[0].places[0]) if kz else LAUNCH_AREA[o]
            avia.append({"obl": o, "lat": la, "lon": lo, "area": area, "t": int(a["t"]), "first": int(a["first"]), "n": a["n"],
                         "platform": a.get("platform") or "тактична авіація", "kab": len(kz),
                         # лінії «звідки пускали» — лише до зон у межах дальності КАБ (≤130 км від району пусків)
                         "to": [[z.places[0].lon, z.places[0].lat] for z in kz
                                if dist_km(_gxy(la, lo), z.places[0].xy) <= 130][:4],
                         "fade": round(min(1.0, (now - a["t"]) / AVIA_LIFE), 2), "ev": a.get("ev", []),
                         "act": int(a["act"]) if a.get("act") else None, "until": int(a["t"] + AVIA_LIFE),
                         "targets": [z.places[0].name for z in kz][:6]})
        return {"now": now, "tracks": out, "zones": zones, "avia": avia, "launches": self.launches.snapshot(now), "levels_tracker": levels, "last_update": self.last_update,
                "log": self.log[-60:], "bal": [e for e in self.bal if now - e["t"] < 3600]}
