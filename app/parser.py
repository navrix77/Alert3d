"""Парсер повідомлень моніторингових каналів (укр/рос) у структуровані спостереження."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .geo import OBLAST_HINTS, Gazetteer, Place, dist_km, norm

TYPES = [
    ("ballistic", re.compile(r"баліст|баллист|искандер|іскандер|кн-23|kn-23")),
    ("jet", re.compile(r"реактивн")),
    ("molniya", re.compile(r"молни|молні")),
    ("kab", re.compile(r"(^|[^а-яіїє])каб|бомб|авиабомб|авіабомб|керован[аі] авіа")),
    ("cruise", re.compile(r"ракет|крилат|крылат|калибр|калібр|х-101|х-59|х-69|х-22|бандерол")),
    ("shahed", re.compile(r"шахед|мопед|бпла|беспилот|безпілот|герань|гербер|дрон")),
]
CLOSE = re.compile(r"не фиксир|не фіксу|отбой|відбій|чисто")
# Безпека: роботу ППО та влучання не публікуємо далі
SAFETY = re.compile(r"пво|ппо|сбит|збит|мінус|минус|взрыв|вибух|прил[её]т|влучан|попадан")
LAUNCH = re.compile(r"пуск|запуск|вылет|зліт|взлет|злет")
THREAT = re.compile(r"угроз|загроз")
AVIATION = re.compile(r"су-34|су-35|ту-95|ту-160|ту-22|миг-31|міг-31")
COUNT = re.compile(r"(\d+)\s*[хx]?\s*(?:реактив|шахед|бпла|ракет|бомб|каб|мопед|ціл|цел|молн|баліст|баллист|дрон)")
SKIP = {
    "реактивний", "реактивный", "реактивні", "реактивних", "реактивные", "реактивных", "шахед", "шахеды", "шахеда",
    "ракета", "ракеты", "ракети", "угроза", "загроза", "молния", "молнія", "ціль", "відбій", "перебувайте", "ударный",
    "ударний", "балістика", "баллистика", "бомбы", "бомби", "увага", "внимание", "курсом", "обстановка", "кабы",
}
POS_PREV = {"районе", "районі", "над", "біля", "возле", "повз", "через", "около", "поблизу", "район"}
FROM_PREV = {"из", "з", "со", "от", "від"}
KH = (49.99, 36.23)
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

    def parse(self, text: str) -> Observation:
        t = norm(text)
        typ = next((k for k, rx in TYPES if rx.search(t)), None)
        m = COUNT.search(t)
        obs = Observation(
            type=typ,
            count=int(m.group(1)) if m else None,
            close=bool(CLOSE.search(t)),
            safety=bool(SAFETY.search(t)),
            launch=bool(LAUNCH.search(t)),
            threat=bool(THREAT.search(t)),
            aviation=bool(AVIATION.search(t)),
        )
        bbox = None
        for rx, name, bb in OBLAST_HINTS:
            if rx.search(t):
                obs.oblast_hint, bbox = name, bb
                break
        words = [w for w in WORD_SPLIT.split(text) if w]
        found: list[tuple[str, list[int]]] = []
        i = 0
        while i < len(words):
            w = words[i]
            prev = norm(words[i - 1]) if i > 0 else ""
            prev2 = norm(words[i - 2]) if i > 1 else ""
            starts_upper = w[:1].isupper()
            if not starts_upper and prev not in POS_PREV | {"в", "на", "у"}:
                i += 1
                continue
            nxt = norm(words[i + 1]) if i + 1 < len(words) else ""
            if norm(w) in SKIP or nxt.startswith(("област", "обл")):
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
                if prev in POS_PREV:
                    role = "p"
                elif prev in FROM_PREV or (prev == "района" and prev2 in FROM_PREV):
                    role = "f"
                found.append((role, ids))
            i += used
        obs.places = self._disambiguate(found, bbox)
        return obs

    def _disambiguate(self, found, bbox) -> list[PlaceRef]:
        P = self.gaz.places
        uniq = [P[ids[0]] for _, ids in found if len(ids) == 1]
        if uniq:
            cen = (sum(p.lat for p in uniq) / len(uniq), sum(p.lon for p in uniq) / len(uniq))
        else:
            cen = KH
        out: list[PlaceRef] = []
        for role, ids in found:
            cand = ids
            if bbox:
                inb = [i for i in ids if bbox[0] <= P[i].lat <= bbox[1] and bbox[2] <= P[i].lon <= bbox[3]]
                cand = inb or ids
            import math

            def score(i: int) -> float:
                p = P[i]
                d = math.hypot((p.lat - cen[0]) * 111, (p.lon - cen[1]) * 73)
                return d - math.log10(1 + p.pop) * 6

            best = min(cand, key=score)
            out.append(PlaceRef(role, P[best]))
        return out
