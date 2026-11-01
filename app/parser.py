"""Парсер повідомлень моніторингових каналів (укр/рос) у структуровані спостереження."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .geo import OBLAST_HINTS, Gazetteer, Place, dist_km, norm

TYPES = [
    ("ballistic", re.compile(r"баліст|баллист|искандер|іскандер|кн-23|kn-23")),
    ("jet", re.compile(r"реактивн|(^|[^а-яіїє])р\.\s*шаболд|(^|[^а-яіїє])р\.\s*шахед")),
    ("molniya", re.compile(r"молни|молні")),
    ("kab", re.compile(r"(^|[^а-яіїє])каб|бомб|авиабомб|авіабомб|керован[аі] авіа")),
    ("cruise", re.compile(r"ракет|крилат|крылат|калибр|калібр|х-101|х-59|х-69|х-22|бандерол")),
    ("shahed", re.compile(r"шахед|мопед|бпла|беспилот|безпілот|герань|гербер|дрон|(^|[^а-яіїє])шах(и|ів)?\b|шаболд|(^|[^а-яіїє])ударн(ий|ик|і|их|ого)\b|(^|[^а-яіїє])ударн(ый|ые|ых)\b")),
]
# статус офіційної тривоги («Сумський район — повітряна тривога / відбій») — не ціль: тривоги беремо з офіційного API
ALERT_STATUS = re.compile(r"(^|[^а-яіїє])развед\w*\.?\s+бпла|розвід\w*\.?\s+бпла|повітряна тривога|воздушная тревога|тривога скасована|відбій (повітряної )?тривоги|рівень:|жовтий рівень|червоний рівень|тривога продовжує")
# «По ударным» / «По Р. Шаболдам» у TLK — закриття по типу
TYPE_CLOSE = re.compile(r"^\s*по\s+(р\.?\s*шаболд\w*|ударн\w*|реактивн\w*|шахед\w*)\s*[.!]*\s*$")
CLOSE = re.compile(r"не фиксир|не фіксу|отбой|відбій|чисто")
# Безпека: роботу ППО та влучання не публікуємо далі
SAFETY = re.compile(r"пво|ппо|сбит|збит|мінус|минус|взрыв|вибух|прил[её]т|влучан|попадан")
LAUNCH = re.compile(r"пуск|запуск|вылет|зліт|взлет|злет")
THREAT = re.compile(r"угроз|загроз")
AVIATION = re.compile(r"су-34|су-35|ту-95|ту-160|ту-22|миг-31|міг-31")
COUNT = re.compile(r"(\d+)\s*[хx]?\s*(?:реактив|шахед|бпла|ракет|бомб|каб|мопед|ціл|цел|молн|баліст|баллист|дрон|ударн)")
DIRS = {"північно-захід": 315, "північно-схід": 45, "південно-захід": 225, "південно-схід": 135, "северо-запад": 315, "северо-восток": 45, "юго-запад": 225, "юго-восток": 135,
        "північ": 0, "південь": 180, "півден": 180, "схід": 90, "сход": 90, "захід": 270, "заход": 270, "север": 0, "юг": 180, "восток": 90, "запад": 270}
COURSE = re.compile(r"(?:(?:курс(?:ом)?|куром|в бік|в сторону|у напрямку|в напрямку)\s+(?:на\s+)?(північно-захід|північно-схід|південно-захід|південно-схід|северо-запад|северо-восток|юго-запад|юго-восток|північ|південь|півден|схід|сход|захід|заход|север|юг|восток|запад)|на\s+(північно-захід|північно-схід|південно-захід|південно-схід|северо-запад|северо-восток|юго-запад|юго-восток|північ|південь|півден|схід|сход|захід|заход|север|юг|восток|запад)[а-яіїє-]*\s+напрям)")
REL = re.compile(r"на\s+(півн|північ|півдн|сход|заход|север|юге|восток|запад)[а-яіїє]*\s+(?:від|от)\s+(\S+)")
REL_AZ = {"півн": 0, "північ": 0, "север": 0, "півдн": 180, "юге": 180, "сход": 90, "восток": 90, "заход": 270, "запад": 270}
REGION_RX = re.compile(r"(щин|ччин|чин)[аиіуою]?$|щині$|ччині$")
DIR_WORDS = {"схід", "сході", "сходу", "захід", "заході", "заходу", "північ", "півночі", "південь", "півдні", "півдня", "восток", "запад", "север", "юг", "центр", "центрі"}
CITY_WORDS = re.compile(r"над містом|по місту|над городом|по городу|для міста|для города|в місті|в городе")
# Канали, для яких «місто» означає Харків
CHANNEL_CITY = {"M": "Харків", "R": "Харків", "TLK": "Харків", "KM": "Харків", "D": "Харків", "CX": "Харків", "SU": "Суми", "PL": "Полтава", "DN": "Дніпро", "KR": "Краматорськ"}
HEADER = re.compile(r"^\s*([А-ЯІЇЄҐ][а-яіїєґ'’]+(?:щина|ччина|еччина|ччини|щини))\s*:", re.M)
SEG_SPLIT = re.compile(r"\n+|(?=🛵)|(?=🚀)|(?=💥)|(?=🟠)|(?=🟡)|(?=🔴)|(?=🟢)|;\s*|\s+-\s+")
SKIP = {
    "реактивний", "реактивный", "реактивні", "реактивних", "реактивные", "реактивных", "шахед", "шахеды", "шахеда",
    "ракета", "ракеты", "ракети", "угроза", "загроза", "молния", "молнія", "ціль", "відбій", "перебувайте", "ударный",
    "ударний", "балістика", "баллистика", "бомбы", "бомби", "увага", "внимание", "курсом", "обстановка", "кабы",
    "ударних", "ударных", "ситуація", "ситуация", "общее", "загальна", "ймовірно", "вероятно", "підпишись",
    "дрони", "дронів", "дронов", "дроны", "бпла", "бпла", "шахедів", "шахедов", "ударні", "ударные", "ракет", "ракетна", "ракетная",
    "небезпека", "опасность", "укриття", "укрытие", "оновлення", "обновление", "моніторинг", "мониторинг", "група", "группа",
    "напрямок", "направление", "курс", "кількість", "количество", "всього", "всего", "також", "также", "повітряна", "воздушная", "тривога", "тревога",
}
POS_PREV = {"районе", "районі", "над", "біля", "возле", "повз", "через", "около", "поблизу", "район"}
FROM_PREV = {"из", "з", "со", "от", "від"}
KH = (49.99, 36.23)
# Райони й мікрорайони міст: монітори пишуть «Ударний на Холодну Гору» — у загальному газетирі таких назв немає
DISTRICTS = [
    (r"холодн\w*\s+гор", "Холодна Гора (Харків)", 49.983, 36.185), (r"залютин", "Залютине (Харків)", 49.975, 36.163),
    (r"нов\w*\s+баварі", "Нова Баварія (Харків)", 49.945, 36.18), (r"північн\w*\s+салтів", "Північна Салтівка (Харків)", 50.055, 36.33),
    (r"салтівк", "Салтівка (Харків)", 50.03, 36.33), (r"олексіївк|алексеевк", "Олексіївка (Харків)", 50.05, 36.21),
    (r"павлов\w*\s+пол", "Павлове Поле (Харків)", 50.04, 36.24), (r"п.?ятихатк", "П'ятихатки (Харків)", 50.08, 36.27),
    (r"\bхтз\b|тракторн\w*\s+завод", "ХТЗ (Харків)", 49.95, 36.37), (r"шишківк", "Шишківка (Харків)", 50.08, 36.21),
    (r"журавлівк", "Журавлівка (Харків)", 50.0, 36.29), (r"\bоснов[аиу]\b", "Основа (Харків)", 49.94, 36.25),
    (r"лис\w*\s+гор", "Лиса Гора (Харків)", 49.95, 36.22), (r"немишл", "Немишля (Харків)", 49.98, 36.31),
    (r"москалівк", "Москалівка (Харків)", 49.97, 36.21), (r"курязь", "Курязь (Харків)", 49.99, 36.11),
    (r"тюрінк", "Тюрінка (Харків)", 50.03, 36.22), (r"сокольник", "Сокольники (Харків)", 50.02, 36.25),
    (r"жуковськ\w*(?!\s+район)", "Жуковського (Харків)", 50.03, 36.29), (r"новожанов", "Новожанове (Харків)", 49.91, 36.28),
    (r"(^|[^а-яіїє])лг(?![а-яіїє])", "Лиса Гора (Харків)", 49.95, 36.22), (r"(^|[^а-яіїє])хг(?![а-яіїє])", "Холодна Гора (Харків)", 49.983, 36.185),
    (r"сортировк|сортуванн", "Південний вокзал (Харків)", 49.99, 36.205), (r"(^|[^а-яіїє])ч\.?\s+лозов", "Черкаська Лозова (Харків)", 50.07, 36.29),
    (r"троєщин|троещин", "Троєщина (Київ)", 50.51, 30.6), (r"оболон", "Оболонь (Київ)", 50.5, 30.5), (r"позняк", "Позняки (Київ)", 50.4, 30.63),
    (r"осокорк", "Осокорки (Київ)", 50.39, 30.62), (r"виноградар", "Виноградар (Київ)", 50.51, 30.42), (r"борщагівк", "Борщагівка (Київ)", 50.42, 30.38),
    (r"теремк", "Теремки (Київ)", 50.37, 30.45), (r"голосіїв", "Голосіїв (Київ)", 50.39, 30.51), (r"\bпод[іо]л", "Поділ (Київ)", 50.46, 30.51),
    (r"лісов\w*\s+масив", "Лісовий масив (Київ)", 50.48, 30.64), (r"святошин", "Святошин (Київ)", 50.46, 30.37),
    (r"труханов\w*\s+остр|труханів\s+остр", "Труханів острів (Київ)", 50.46, 30.54), (r"дарниц", "Дарниця (Київ)", 50.45, 30.62),
]
DISTRICT_RX = [(re.compile(rx), n, la, lo) for rx, n, la, lo in DISTRICTS]
WORD_SPLIT = re.compile(r"[\s,.;:!?()«»\"/]+")


@dataclass
class PlaceRef:
    role: str  # t — у списку «курсом на», p — поточна позиція, f — звідки
    place: Place


@dataclass
class Observation:
    type: str | None
    count: int | None
    places: list[PlaceRef] = field(default_factory=list)
    close: bool = False
    safety: bool = False
    launch: bool = False
    threat: bool = False
    aviation: bool = False
    oblast_hint: str | None = None
    course: float | None = None

    @property
    def kind(self) -> str:
        if self.safety:
            return "filtered"
        if self.close:
            return "close"
        if self.type == "kab" or (self.aviation and not self.type):
            return "zone"
        if self.type and self.places:
            return "track"
        return "info"


class Parser:
    def __init__(self, gaz: Gazetteer | None = None) -> None:
        self.gaz = gaz or Gazetteer.load()

    def segments(self, text: str) -> list[str]:
        """Ділить зведення на окремі повідомлення про цілі; заголовок області («Полтавщина:») переносить на наступні рядки."""
        out, header = [], ""
        for raw in SEG_SPLIT.split(text):
            seg = (raw or "").strip(" \t-•–—")
            if not seg:
                continue
            m = HEADER.match(seg)
            if m:
                header = m.group(1)
                seg = seg[m.end():].strip()
                if not seg:
                    continue
            out.append(f"{seg} ({header})" if header else seg)
        return out or [text]

    def parse(self, text: str, channel: str | None = None, ctx: tuple[float, float] | None = None) -> Observation:
        t = norm(text)
        typ = next((k for k, rx in TYPES if rx.search(t)), None)
        m = COUNT.search(t)
        if ALERT_STATUS.search(t):
            typ = None
        if TYPE_CLOSE.match(t):
            typ = "jet" if re.search(r"шаболд|реактивн", t) else "shahed"
            return Observation(type=typ, count=None, close=True)
        obs = Observation(
            type=typ,
            count=int(m.group(1)) if m and 0 < int(m.group(1)) <= 15 else None,
            close=bool(CLOSE.search(t)),
            safety=bool(SAFETY.search(t)),
            launch=bool(LAUNCH.search(t)),
            threat=bool(THREAT.search(t)),
            aviation=bool(AVIATION.search(t)),
        )
        bbox = None
        self._chan_bbox = False
        for rx, name, bb in OBLAST_HINTS:
            if rx.search(t):
                obs.oblast_hint, bbox = name, bb
                break
        if bbox is None and channel:
            from .config import CHANNEL_REGION
            from .geo import oblasts
            reg = CHANNEL_REGION.get(channel)
            if reg:
                for name, _polys, bb in oblasts().items:
                    if name == reg:
                        obs.oblast_hint, bbox = name, (bb[1] - 0.15, bb[3] + 0.15, bb[0] - 0.2, bb[2] + 0.2)
                        self._chan_bbox = True
                        break
        # мікрорайони міст — до загального пошуку; їхні слова вирізаємо, щоб не знайти «Гору» чи «Основу» деінде
        dist_found = []
        tl = norm(text)
        from .config import CHANNEL_REGION
        creg = CHANNEL_REGION.get(channel or "", "")
        for rx, dn, la, lo in DISTRICT_RX:
            city = "Київ" if "(Київ)" in dn else "Харків"
            # мікрорайон рахуємо лише в каналах цього міста/області або коли місто назване в тексті
            if not ((city == "Харків" and (creg == "Харківська" or "харк" in tl)) or (city == "Київ" and (creg in ("Київська", "Київ") or "київ" in tl or "киев" in tl))):
                continue
            m_ = rx.search(tl)
            if m_:
                before = tl[max(0, m_.start() - 25):m_.start()].split()
                role = "p" if before and before[-1] in POS_PREV else "t"
                dist_found.append((m_.start(), PlaceRef(role, Place(dn, la, lo, "D", 30000))))
                text = text[:m_.start()] + " " * (m_.end() - m_.start()) + text[m_.end():] if len(text) == len(tl) else text
        arrow = re.search(r"\s(?:>|→|->|=>|➡️?)\s", text)
        cut = len([w for w in (re.sub(r"[^\w'’\-]", "", x) for x in WORD_SPLIT.split(text[:arrow.start()])) if w]) if arrow else None
        words = [re.sub(r"[^\w'’\-]", "", w) for w in WORD_SPLIT.split(text)]
        words = [w for w in words if w]
        found: list[tuple[str, list[int]]] = []
        i = 0
        while i < len(words):
            w = words[i]
            prev = norm(words[i - 1]) if i > 0 else ""
            prev2 = norm(words[i - 2]) if i > 1 else ""
            starts_upper = w[:1].isupper()
            if not starts_upper or REGION_RX.search(norm(w)) or norm(w) in DIR_WORDS:
                i += 1
                continue
            nxt = norm(words[i + 1]) if i + 1 < len(words) else ""
            if norm(w) in SKIP or nxt.startswith(("област", "обл", "громад")):
                i += 1
                continue
            ids, used = None, 1
            if i + 1 < len(words) and words[i + 1][:1].isalpha():
                ids = self.gaz.lookup_bigram(w, words[i + 1])
                if ids:
                    used = 2
            if not ids:
                ids = self.gaz.lookup(w)
            if ids:
                role = "t"
                if cut is not None:
                    role = "p" if i < cut else "t"
                elif i == 0 and not obs.close:
                    role = "p"  # «Великий Вистороп — шахед»: пункт на початку без прийменника — де ціль зараз
                elif prev in POS_PREV:
                    role = "p"
                elif prev in FROM_PREV or (prev == "района" and prev2 in FROM_PREV):
                    role = "f"
                found.append((role, ids))
            i += used
        obs.places = [r for _, r in sorted(dist_found, key=lambda x: x[0])] + self._disambiguate(found, bbox, ctx)
        mc = COURSE.search(t)
        if mc:
            g = mc.group(1) or mc.group(2)
            for k, az in DIRS.items():
                if g.startswith(k):
                    obs.course = float(az)
                    break
        # «на сході від Харкова» — позиція за 20 км у вказаному напрямку від пункту
        mr = REL.search(t)
        if mr:
            ids = self.gaz.lookup(mr.group(2))
            if ids:
                base = self._disambiguate([("p", ids)], bbox)[0].place
                from .geo import from_xy, move
                az = next(v for k, v in REL_AZ.items() if mr.group(1).startswith(k))
                lat, lon = from_xy(*move(base.xy, az, 20))
                rel = Place(f"{base.name} ({['пн', '', 'сх', '', 'пд', '', 'зх'][az // 45]})", lat, lon, base.kind, base.pop)
                obs.places = [p for p in obs.places if p.place.name != base.name or p.role != "f"]
                obs.places.insert(0, PlaceRef("p", rel))
        # «над містом» у міському каналі
        if channel in CHANNEL_CITY and CITY_WORDS.search(t) and not any(p.role == "p" for p in obs.places):
            ids = self.gaz.lookup(CHANNEL_CITY[channel])
            if ids:
                city = max((self.gaz.places[i] for i in ids), key=lambda p: p.pop)
                obs.places.insert(0, PlaceRef("p", city))
        return obs

    def _disambiguate(self, found, bbox, ctx=None) -> list[PlaceRef]:
        import math
        P = self.gaz.places
        uniq = [P[ids[0]] for _, ids in found if len(ids) == 1]
        if uniq:
            cen = (sum(p.lat for p in uniq) / len(uniq), sum(p.lon for p in uniq) / len(uniq))
            if ctx:  # контекст усього повідомлення / недавніх повідомлень каналу
                cen = ((cen[0] + ctx[0]) / 2, (cen[1] + ctx[1]) / 2)
        else:
            cen = ctx or KH
        out: list[PlaceRef] = []
        for role, ids in found:
            cand = ids
            if bbox:
                inb = [i for i in ids if bbox[0] <= P[i].lat <= bbox[1] and bbox[2] <= P[i].lon <= bbox[3]]
                if not inb and getattr(self, "_chan_bbox", False):
                    # регіональний канал назвав щось, чого в його регіоні немає (острів, урочище, вулиця) —
                    # не «телепортуємо» ціль у тезку за сотні кілометрів
                    def off(i):
                        q = P[i]
                        dy = max(bbox[0] - q.lat, 0, q.lat - bbox[1]) * 111
                        dx = max(bbox[2] - q.lon, 0, q.lon - bbox[3]) * 72
                        return math.hypot(dx, dy)
                    if min(off(i) for i in ids) > 60:
                        continue
                cand = inb or ids
            import math

            def score(i: int) -> float:
                p = P[i]
                d = math.hypot((p.lat - cen[0]) * 111, (p.lon - cen[1]) * 73)
                # місто (≥20 тис.) майже завжди важливіше за одноіменне село, якщо контекст прямо не вказує на село
                city = (25 if ctx or uniq else 70) if p.pop >= 20000 else 0
                return d - math.log10(1 + p.pop) * (3 if ctx else 6) - city

            best = min(cand, key=score)
            out.append(PlaceRef(role, P[best]))
        return out
