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
    (re.compile(r"запоріз|запорож|^\W*запоріжжя\s*:|\(запоріжжі\)|(?<![\w])на запоріжжі"), "Запорізька", (46.6, 48.3, 34.2, 37.3)),
    (re.compile(r"київщ|киевск(?!\w*\s+(?:р-н|район))|київськ(?!\w*\s+(?:р-н|район))"), "Київська", (49.2, 51.6, 29.2, 32.2)),  # «Київський район» є й в Одесі
]
RENAMED = {
    "козачка": "Козача Лопань", "казачка": "Козача Лопань", "первомайський": "Златопіль", "первомайский": "Златопіль", "красноград": "Берестин", "комсомольське": "Слобожанське", "комсомольское": "Слобожанське",
    "новомосковськ": "Самар", "новомосковск": "Самар", "дніпропетровськ": "Дніпро", "днепропетровск": "Дніпро",
    "кіровоград": "Кропивницький", "кировоград": "Кропивницький", "артемівськ": "Бахмут", "артемовск": "Бахмут",
    "красноармійськ": "Покровськ", "красноармейск": "Покровськ", "димитров": "Мирноград", "орджонікідзе": "Покров",
    "комсомольськ": "Горішні Плавні", "котовськ": "Подільськ", "червоноград": "Шептицький", "червоноград": "Шептицький",
    "новоград-волинський": "Звягель", "переяслав-хмельницький": "Переяслав", "володимир-волинський": "Володимир",
    "северодонецк": "Сіверськодонецьк", "южне": "Південне", "южноукраїнськ": "Південноукраїнськ", "южноукраинск": "Південноукраїнськ",
}
# російські назви двослівних міст (канали пишуть і так): форма → українська назва
RU_BIGRAM = {f"{a} {b}": uk for uk, forms in {
    "Біла Церква": [("белая", "церковь"), ("белую", "церковь"), ("белой", "церкви"), ("белая", "церква")],
    "Кривий Ріг": [("кривой", "рог"), ("кривого", "рога"), ("кривом", "роге")],
    "Новий Буг": [("новый", "буг")], "Нова Каховка": [("новая", "каховка"), ("новую", "каховку")],
    "Біла Криниця": [("белая", "криница")], "Стара Синява": [("старая", "синява")],
    # описка «Нова Гелещина» (ppopoltavanightfighters 07.11 17:04, 17:09, 21:22 …, 7 повідомлень; PL і PoltavaRanger тієї ж
    # хвилі пишуть «Нову Галещину», «Нової Галещини»): без цього ціль ставало в село Нова за ≈190 км
    "Нова Галещина": [("нова", "гелещина"), ("нову", "гелещину"), ("нової", "гелещини")],
    # 10.11: рос. форми (D, ND): «на Великую Гомольшу» (о/і не зводить phon), «Золотой Колодезь» ставав Золоте на Луганщині
    "Велика Гомільша": [(a, b) for a in ("великая", "великую", "великой", "большая", "большую", "большой")
                        for b in ("гомольша", "гомольшу", "гомольши", "гомольше", "гомільшу", "гомільші")],
    "Золотий Колодязь": [("золотой", "колодезь"), ("золотий", "колодезь"), ("золотого", "колодезя"), ("золотой", "колодец")],
} .items() for a, b in forms}
RU_ADJ = [("больш", "велик"), ("малень", "мал"), ("мал", "мал"), ("стар", "стар"), ("ст", "стар"), ("нов", "нов"), ("верхн", "верхн"),
          ("нижн", "нижн"), ("каменн", "кам'ян"), ("казач", "козач"), ("русск", "руськ"), ("бел", "біл"), ("черн", "чорн"),
          ("зелён", "зелен"), ("зелен", "зелен"), ("сух", "сух"), ("средн", "середн"), ("крив", "крив")]
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
    if a == b or (a[:-1] == b and a[-1:] in "мвх"):  # закінчення: Балабиному, Дергачів, Чернівцях
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
        # населені пункти, яких немає в КАТОТТГ-вибірці, але монітори їх пишуть (перевірено за журналом)
        # 03.11: «Ракета Золочев/Ольшаны», «Вектор Ольшаны/Солоницевка/Люботин» (TLK) — селище Ольшани під Харковом
        for names, pl in [(["Ольшани", "Ольшаны"], Place("Ольшани", 50.0514, 35.8756, "X", 4_000)),
                          # «на Малую Даниловку» (R, D, CX, KM): селище під північно-західною межею Харкова
                          (["Мала Данилівка", "Малая Даниловка", "Мала Даниловка"], Place("Мала Данилівка", 50.063, 36.165, "X", 4_000)),
                          # 04.11: «над Екопарком, курсом на Лісне» (KM) — Фельдман Екопарк у с. Лісне під Харковом (Харківський р-н);
                          # Лісне під Харковом важливіше за тезку біля Зміїва; екопарк — у межах цього селища (координати приблизні)
                          (["Лісне", "Лесное"], Place("Лісне", 50.114, 36.275, "X", 9_000)),
                          # 08.11: «БОМБЫ курсом дальше на Купянск-Узловой, Березовку» (ND) — рос. форма не зводилась до Куп'янськ-Вузловий
                          (["Купянск-Узловой", "Купянськ-Вузловий", "Куп'янськ-Вузловий"], Place("Куп’янськ-Вузловий", 49.6603, 37.6475, "X", 4_000)),
                          (["Екопарк", "Экопарк", "Фельдман Екопарк", "Фельдман Экопарк", "Фельдман-Екопарк"], Place("Екопарк (Лісне)", 50.114, 36.275, "X", 4_000)),
                          # 08.11: журнал 05–08.11 — усі 14 згадок «Десна» з відомою областю стосуються селища на Чернігівщині
                          # («Десна/Остер» PhantomChe, horizon_of_war; «на Чернігівщині … на Десну» UkraineRadar_24_7; KL «(Чернігівщина)»),
                          # жодної — тезки під Вінницею; без області («⟐1 Десна» monikppy, «повз Десну» eRadarrua) ставило Вінниччину.
                          # Координати з КАТОТТГ (data/places_katottg.json, UA74)
                          (["Десна"], Place("Десна", 50.9283, 30.759, "X", 9_000)),
                          # 09.11: харківські канали скорочують: «2 ударных Приколотное/Бурлук» (TLK, R) — сусідні Приколотне і
                          # Великий Бурлук; «Ударный на Ольшаны/Мерчик» (TLK; M, R тієї ж хвилі: «на Старий Мерчик»).
                          # Сіл «Бурлук» і «Мерчик» у КАТОТТГ немає; координати з КАТОТТГ (UA63)
                          (["Великий Бурлук", "Бурлук"], Place("Великий Бурлук", 50.0607, 37.3836, "X", 4_000)),
                          (["Старий Мерчик", "Мерчик", "Старый Мерчик"], Place("Старий Мерчик", 49.976, 35.7772, "X", 4_000))]:
            near = [i for i in g.idx.get(norm(pl.name), []) if abs(g.places[i].lat - pl.lat) < 0.05 and abs(g.places[i].lon - pl.lon) < 0.05]
            if pl.pop >= 4_000 and near:  # відоме селище під Харковом важить більше за тезок в області
                for i in near:
                    g.places[i].pop = max(g.places[i].pop, pl.pop)
            if not near:
                g.add(names, pl)
            else:  # уже є в КАТОТТГ: лише додаємо російську форму назви
                for n in names:
                    g.idx.setdefault(norm(n), [])
                    if near[0] not in g.idx[norm(n)]:
                        g.idx[norm(n)].append(near[0])
        return g

    # --- відмінки: спроба звести словоформу до називного
    @staticmethod
    def candidates(w: str) -> list[str]:
        c = [w]
        if len(w) < 4:
            m = re.match(r"^(.+)о([^аеиіоуюяєїь'\- ])$", w)
            return c + [m.group(1) + "і" + m.group(2)] if m else c  # «Рог» → Ріг
        b, b2, e, e2 = w[:-1], w[:-2], w[-1], w[-2:]
        # 10.11: рос. чоловічий «-ов/-ев» = укр. «-ів» — раніше за форми множини: «БОМБЫ курсом на Орехов» (D) → Оріхів,
        # а не через «Орехови» фонетично село Оріхове на Луганщині
        if w.endswith(("ов", "ев")) and len(w) >= 5:
            c.append(w[:-2] + "ів")
        # рос. орудний «-ой» від «-а»: «над Бобровкой на Харьков» (ND) → Бобрівка
        if w.endswith("кой") and len(w) >= 6:
            c += [w[:-2] + "а", (w[:-2] + "а").replace("ов", "ів")]
        if w.endswith(("евом", "овом", "ёвом")) and len(w) >= 7:  # рос. орудний: «над Змиевом» → Зміїв, не Зміївка
            c.append(w[:-4] + "ів")
        # рос. «-ица» = укр. «-иця»: «на Гнилицу» → Гнилиця (Куп'янщина), а не Гнилець на Черкащині через фонетичний ключ (08.11)
        if re.search(r"иц[аеуы]$", w) and len(w) >= 6:
            c.append(w[:-1] + "я")
        # рос. середній рід «-ее» = укр. «-є/-е», «Под-» = «Під-»: «на Подсреднее/Подсереднее» → Підсереднє (08.11)
        if w.endswith("ее") and len(w) >= 6:
            st = re.sub(r"^под", "під", w[:-2])
            c += [st + "є", st + "е"]
            if st.startswith("підср"):  # типова описка моніторів «Подсреднее» без «е»
                c += ["підсер" + st[5:] + "є"]
        # описка «Хмельницього» (пропущене «к»): «наближається до Хмельницього зі сходу» → Хмельницький, а не Хмільниця (08.11)
        if w.endswith("ницього"):
            c.append(w[:-4] + "ький")
        # укр. родовий множини «-ок» від назв на «-ки»: «в районі Городні/Ріпок» → Ріпки (08.11)
        if w.endswith("ок") and len(w) >= 5:
            c.append(w[:-2] + "ки")
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
        if w.endswith(("ами", "ями", "ими")):  # орудний множини: «Новими Санжарами» → Нові Санжари
            c += [w[:-3] + "и", w[:-3] + "і"]
        if e2 == "их":  # родовий множини прикметника: «Великих Сорочинців», «Жовтих Вод»
            c += [b2 + "і", b2 + "ий"]
        if w.endswith("ців"):  # «Сорочинців» → Сорочинці
            c.append(w[:-1])
        if e2 == "ый":  # рос. «Старый Салтов»
            c.append(b2 + "ий")
        if e2 in ("ою", "ею", "єю"):  # орудний: «над Шосткою» → Шостка, «над Охтиркою» → Охтирка
            c += [b2 + "а", b2 + "я"]
        if e2 == "ую":  # рос. жіночий знахідний: «Лозовую» = Лозова (не Лозове — те було б «Лозовое»)
            return [w, b2 + "а", b2 + "ая"]
        if e2 in ("ое", "ій", "ий", "ые", "ої", "ом", "ем", "ой", "ая"):
            c += [b2 + x for x in ("ое", "ий", "е", "а", "о", "ій", "ів", "ов", "ки", "ка")]
        if e2 in ("ом", "ем"):
            c.append(b2)
        if w.endswith(("ова", "ева")):
            c.append(w[:-1])
        if w.endswith(("ові", "еві")):
            c.append(w[:-1])
        if w.endswith(("ино", "ово", "ево")):  # рос. «Коробочкино», «Голубово» → Коробочкине
            c.append(w[:-1] + "е")
        if w.endswith("ого"):
            c += [w[:-3] + "е", w[:-3] + "ий"]
        # укр. родовий/орудний від «-ів/-їв»: Богодухова, Чугуєва, Богодуховом
        # прикметник району: «Вовчанський/Вовчанського район» → Вовчанськ
        for suf in ("ський", "цький", "ського", "цького", "ському", "цькому"):
            if w.endswith(suf):
                c.append(w[: -len(suf)] + suf[:3])
                c.append(w[: -len(suf)])  # «Ізюмський район» → Ізюм, «Чугуївський» → Чугуїв
        for suf, rep in (("ов", "ів"), ("ова", "ів"), ("ева", "ів"), ("єва", "їв"), ("овом", "ів"), ("євом", "їв"), ("евом", "ів"), ("евым", "ів"), ("ові", "ів"), ("єві", "їв"), ("ову", "ів"), ("еву", "ів"), ("єву", "їв")):
            if w.endswith(suf):
                c.append(w[: -len(suf)] + rep)
        for x in list(c):  # рос. «Харьков» → «Харьків» → Харків: м'який знак перед приголосним в укр. назві відсутній
            if "ь" in x[:-1]:
                c.append(re.sub(r"ь(?=[бвгґджзклмнпрстфхцчшщ])", "", x))
        for x in list(c):  # ікавізм у закритому складі: рос. «Рогу»/«Рог» → Ріг, «Кривой Рог»
            m = re.match(r"^(.+)о([^аеиіоуюяєїь'\- ]{1,2})$", x)
            if m:
                c.append(m.group(1) + "і" + m.group(2))
        seen, out = set(), []
        for x in c:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out

    def lookup(self, word: str) -> list[int] | None:
        hit = self._lookup(word)
        # 09.11: рос. «ё» після м'якого приголосного буває укр. «о»: «дальше на Солёное» (dnepr_nagladach, radar_sich) → Солоне;
        # norm() зводить «ё» до «е», і «Соленое» не знаходилось. Лише запасний шлях: «Зелёное» лишається Зелене
        if hit is None and "ё" in word.lower():
            hit = self._lookup(word.lower().replace("ё", "о"))
        # 11.11 ніч: те саме без «ё»: «Реактив на Соленое от Славгорода» (dnepr_nagladach) → Солоне
        if hit is None and re.match(r"(?i)солен", word):
            hit = self._lookup("солон" + word[5:].lower())
        # рос. «-олье» = укр. «-ілля»: «на Доброволье, Верхнюю Самару» (ND 11.11) → Добровілля (Лозівщина)
        if hit is None and re.search(r"(?i)олье$|олья$|олью$", word):
            hit = self._lookup(word[:-4].lower() + "ілля")
        # 12.11: «на Сахновшину», «южнее Сахновшины» (ш замість щ) у Nablydatel_Dozor і NochnojDozorKh ночами 09, 10, 11 і
        # 12.11 (12 постів: «от Краснопавловки на Сахновшину, Зачепиловку»): назва губилась. Лише ця основа
        if hit is None and re.match(r"(?i)сахновшин", word):
            hit = self._lookup("сахновщин" + word[9:].lower())
        return hit

    def _lookup(self, word: str) -> list[int] | None:
        w = re.sub(r"[^а-яіїєґыэъ'\- ]", "", norm(word))
        # 09.11: рос. «Константиновка» = укр. «Костянтинівка» («БОМБЫ курсом на Константиновку, Дружковку…», D)
        if w.startswith("константин"):
            w = "костянтин" + re.sub(r"^ов", "ів", w[len("константин"):])
        # 10.11: «Павлик» — розмовна назва Павлограда в моніторах Дніпра (dnepr_nagladach «Реактив от Павлика на Игрень»,
        # «Бандероль от Павлика на Самар», «Павлик вектор КАБов»; novik_nagladach «Самар бандероль от Павлика»; radar_sich
        # «Снкв: Реактив от Павлика на Кислянку»), журнал 07–10.11, 14 повідомлень, 3 канали. Раніше: Павлівка/Павлики
        # за 50–200 км. Лише точні форми (село Павлики на Полтавщині не чіпаємо)
        if w in ("павлик", "павлика", "павлику", "павликом", "павлике"):
            w = "павлоград"
        # перейменовані міста: канали досі пишуть старі назви
        for c in self.candidates(w) if len(w) >= 4 else []:
            if c in RENAMED:
                hit = self.idx.get(norm(RENAMED[c]))
                if hit:
                    return hit
        if len(w) < 3 or w in REGION_WORDS:
            return None
        # точна назва («Лозове») — не змішуємо з іншими формами («Лозова»); але «Глухова», «Чугуєва» — це передусім
        # родовий від міст на -ів (Глухів), а не село Глухова на Житомирщині: тоді шукаємо разом з іншими формами
        if w in self.idx and not w.endswith(("ова", "ева", "єва")):
            # «на Затоку» / «в сторону Затоки»: точна назва «Затоки» (село на Поділлі) — але це й родовий від Затока;
            # тоді беремо обидві форми, а вибір робить контекст повідомлення/каналу
            # 08.11: «у напрямку Черкас» — родовий від Черкаси (місто), а не село Черкас на Київщині: точна назва лише
            # дрібні села, а «+и/і» дає місто ≥20 тис. → місто разом з ними (вибір робить контекст; місто важить більше)
            if len(w) >= 5 and w[-1] not in "аеиіоуюяєїь'":
                alt = [i for c in (w + "и", w + "і") for i in self.idx.get(c, []) if self.places[i].pop >= 20000]
                if alt and max(self.places[i].pop for i in self.idx[w]) < 5000:
                    return alt + self.idx[w]
            if len(w) >= 5 and w[-1] in "иі" and w[-2] not in "аеиіоуюяєї":
                alt = [i for c in (w[:-1] + "а", w[:-1] + "я") for i in self.idx.get(c, [])]
                if alt and max(self.places[i].pop for i in alt) >= max(self.places[i].pop for i in self.idx[w]):
                    return self.idx[w] + [i for i in alt if i not in self.idx[w]]
                # 11.11 ніч: «реактивний від Рудки до М.К.» (PhantomChe) — родовий від села Рудка під Черніговом, а не
                # містечко Рудки на Львівщині (550 км). Точна назва лише в одній-двох областях, а форма «-а/-я» є в інших:
                # беремо обидві, вибір робить регіон каналу/контекст (місто більшого розміру однаково важить у score)
                if alt and len({self.places[i].lat // 1 for i in self.idx[w]}) <= 2 and len(self.idx[w]) <= 2:
                    return self.idx[w] + [i for i in alt if i not in self.idx[w]]
            # 10.11: «на Підгородне/Слобожанське» (dnipromonitor) — укр. «-нє» без «є»; точна назва «Підгородне» є лише на
            # Донеччині, тож місто Підгороднє під Дніпром губилось. Додаємо форму на «-є», вибір робить контекст
            if len(w) >= 6 and w.endswith("не") and w[:-1] + "є" in self.idx:
                return self.idx[w] + [i for i in self.idx[w[:-1] + "є"] if i not in self.idx[w]]
            return self.idx[w]
        hits: list[int] = []
        for c in self.candidates(w):
            if c in self.idx:
                hits += [i for i in self.idx[c] if i not in hits]
        if hits:
            # рос. форма може збігтися з іншим українським селом: «Балаклею» → Балаклея (Черкащина), хоча мова про
            # Балаклію (Харківщина). Додаємо фонетичні збіги, вибір робить контекст каналу (03.11)
            ru = bool(re.search(r"[ыэёъ]", w)) or w.endswith(("ею", "ое", "ая", "ый", "ой", "ее", "ье", "ые"))
            for c in self.candidates(w)[:4] if ru else []:
                for i in self.kidx.get(phon(c), []):
                    if i not in hits:
                        hits.append(i)
            return hits
        # родовий множини лише коли сама форма не знайдена: «від Ромнів» → Ромни, «Жуків» → Жуки
        # (а «Васильків», «Бердичів» — це називний, вони знаходяться вище)
        if w.endswith("ів") and len(w) >= 5:
            for c in (w[:-2] + "и", w[:-2] + "і"):
                if c in self.idx:
                    return self.idx[c]
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
                if d < bd and _skel_ok(k, kk):
                    best, bd = kk, d
            if best:
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
        al = RU_BIGRAM.get(f"{A} {B}")
        if al and norm(al) in self.idx:
            return self.idx[norm(al)]
        ca, cb = self.candidates(A), self.candidates(B)
        # рос. прикметники двослівних назв: «Большую Даниловку» → Велика Данилівка, «Казачью Лопань» → Козача Лопань,
        # «Каменную Яругу» → Кам'яна Яруга, «Ст Салтов» → Старий Салтів (журнал TLK, D, R, CX)
        for ru, uk in RU_ADJ:
            end = A[len(ru):]
            if A.startswith(ru) and end in ("", "ая", "ую", "ой", "ей", "ья", "ью", "яя", "юю", "ый", "ий", "ое", "ее", "ые", "ие", "ого", "его", "ом", "ем", "ую", "их", "ых", "а", "ий", "е", "і", "ої", "у"):
                fem = end in ("ая", "ую", "ой", "ей", "ья", "ью", "яя", "юю") or end == ""
                ca = ca + [uk + e for e in (("а", "ий", "е") if fem else ("ий", "е", "а", "і"))]
                if uk in ("верхн", "нижн", "середн"):  # м'які прикметники: «Верхнюю Самару» → Верхня Самара (ND 11.11), а не місто Самар
                    ca = ca + [uk + e for e in (("я", "ій", "є") if fem else ("ій", "є", "я", "і"))]
        cb = cb + [c.replace("ов", "ів").replace("ев", "ів") for c in cb if "ов" in c or "ев" in c]
        if A.endswith(("их", "іх")) and B.endswith("ів") and len(B) >= 5:  # «з-під Кінських Роздорів» → Кінські Роздори
            cb = cb + [B[:-2] + "и", B[:-2] + "і"]  # (eyes_everywhere_ua, radar_sich 06.11 13:37; без цього — село Роздори)
        if len(B) <= 4 and B[-1:] not in "аеиіоуюяь":  # «Жовтих Вод» → Жовті Води
            cb = cb + [B + "и", B + "і"]
        for x in ca:
            for y in cb:
                k = f"{x} {y}"
                if k in self.idx:
                    return self.idx[k]
        for x in ca:
            for y in cb:
                k = phon(f"{x} {y}")
                if len(k) >= 8 and k in self.kidx:
                    return self.kidx[k]
        # рос. написання двослівної назви: «Черкасскую Лозовую» → Черкаська Лозова
        if len(A) < 4 or len(B) < 4:
            return None
        bk = self.__dict__.get("_bk")
        if bk is None:
            bk = self._bk = {}
            for k, v in self.kidx.items():
                if " " in k:
                    bk.setdefault(re.sub(r"(.)\1+", r"\1", k), []).extend(v)
        for x in ca:
            for y in cb:
                k = re.sub(r"(.)\1+", r"\1", phon(f"{x} {y}"))
                if k in bk:
                    return bk[k]
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


class Raions(Oblasts):
    """Межі районів (data/raions.geojson) — для радіо «Моя область» і «Поруч зі мною»."""

    def __init__(self) -> None:  # noqa: D107
        fc = json.loads((DATA / "raions.geojson").read_text(encoding="utf-8"))
        self.items = []
        for f in fc["features"]:
            g = f["geometry"]
            polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
            xs = [x for pl in polys for x, _ in pl[0]]
            ys = [y for pl in polys for _, y in pl[0]]
            self.items.append((f["properties"]["n"], polys, (min(xs), min(ys), max(xs), max(ys))))


@lru_cache(maxsize=1)
def raions() -> Raions:
    return Raions()
