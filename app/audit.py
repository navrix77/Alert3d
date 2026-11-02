"""Самоаналіз: кожне повідомлення перевіряємо на правдоподібність і записуємо аномалії.
Те, що повторюється, — матеріал для навчання (неправильні населені пункти, «телепорти» цілей, курс за сотні км,
канал пише не про свою область). Джерелам із «телепортами» автоматично знижуємо довіру."""
from __future__ import annotations

import collections
import json
import os
import time
from pathlib import Path

from .geo import dist_km, from_xy

_DIR = Path(os.getenv("PERSIST_DIR") or Path(__file__).resolve().parent.parent / "data")
FILE = _DIR / "audit.jsonl"


class Audit:
    def __init__(self) -> None:
        self.recent: collections.deque = collections.deque(maxlen=400)
        self.count: collections.Counter = collections.Counter()
        self.by_src: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        self.by_place: collections.Counter = collections.Counter()
        self.seen = 0

    def add(self, kind: str, src: str, text: str | None, **kw) -> None:
        rec = {"t": int(time.time()), "kind": kind, "src": src, "text": (text or "")[:200], **kw}
        self.recent.append(rec)
        self.count[kind] += 1
        self.by_src[src][kind] += 1
        if kw.get("place"):
            self.by_place[f'{kind}:{kw["place"]}'] += 1
        if os.getenv("PYTEST_CURRENT_TEST"):
            return
        try:
            with FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def check(self, tr, obs, src: str, region: str | None, obl_of_xy, nominal: float, brain=None, learn=True) -> None:
        """Викликається після кожного оновлення треку."""
        self.seen += 1
        text = getattr(obs, "raw", None)
        if len(tr.obs) >= 2:
            a, b = tr.obs[-2], tr.obs[-1]
            if b.t == tr.last.t and b.src == src:
                d = dist_km((a.x, a.y), (b.x, b.y))
                dt = max(30.0, b.t - a.t)
                v = d / dt * 3600
                if d > 25 and v > nominal * 3:
                    self.add("teleport", src, text, track=tr.id, type=tr.type, km=round(d), kmh=round(v),
                             place=b.label, prev=a.label)
                    if brain and learn:
                        brain.rel_update(src, False, 0.3)
        if tr.route and tr.obs:
            here = (tr.last.x, tr.last.y)
            far = max(dist_km(here, p.xy) for p in tr.route)
            lim = 700 if tr.type in ("cruise", "ballistic") else 450
            if far > lim:
                self.add("far_course", src, text, track=tr.id, type=tr.type, km=round(far),
                         place=tr.route[-1].name, at=tr.last.label)
        if region and tr.obs and tr.last.src == src:
            la, lo = from_xy(tr.last.x, tr.last.y)
            o = obl_of_xy(lo, la)
            if o and not region.startswith(o[:5]):
                self.add("off_region", src, text, track=tr.id, place=tr.last.label, obl=o, region=region)

    def state(self) -> dict:
        top_src = sorted(((s, sum(c.values())) for s, c in self.by_src.items()), key=lambda x: -x[1])[:15]
        return {"checked": self.seen, "count": dict(self.count), "top_sources": top_src,
                "top_places": self.by_place.most_common(20), "recent": list(self.recent)[-60:]}


AUDIT = Audit()
