"""Безперервне навчання на сервері (кожні 5 хв), лише на вимірах і з доказами:
1) реальна швидкість кожного типу цілей — з послідовних фіксацій у різних пунктах (медіана, у межах 0.6–1.5× паспортної);
2) надійність типу в кожного каналу — як часто його «реактивні» виявляються дублем шахеда (і навпаки);
3) статистика злиттів дублікатів, аномалій аудиту й точності прогнозу — для щоденного самоаналізу.
Стан зберігається у learn.json (PERSIST_DIR або data/)."""
from __future__ import annotations

import asyncio
import collections
import json
import logging
import os
import statistics
import time
from pathlib import Path

from .geo import dist_km

log = logging.getLogger("learner")
FILE = Path(os.getenv("PERSIST_DIR") or Path(__file__).resolve().parent.parent / "data") / "learn.json"


class Learner:
    def __init__(self, tracker, brain=None) -> None:
        self.tr, self.brain = tracker, brain
        self.base = {k: v["speed"] for k, v in tracker_types().items()}
        self.speeds: dict[str, list] = collections.defaultdict(list)   # тип -> [[км/год, трек, від, до, t]]
        self.seen: dict = {}  # впорядковано за часом додавання
        self.type_conf: dict[str, dict] = collections.defaultdict(lambda: {"ok": 0, "dup": 0})
        self.merges: collections.Counter = collections.Counter()
        self.runs, self.last = 0, 0.0
        self.log: collections.deque = collections.deque(maxlen=60)
        self._load()

    # ---------- збереження
    def _load(self):
        try:
            d = json.loads(FILE.read_text(encoding="utf-8"))
            for k, v in d.get("speeds", {}).items():
                self.speeds[k] = v[-300:]
            for k, v in d.get("type_conf", {}).items():
                self.type_conf[k] = v
            self.apply_speeds()
        except Exception:
            pass

    def _save(self):
        try:
            FILE.write_text(json.dumps({"speeds": self.speeds, "type_conf": self.type_conf, "t": int(time.time())},
                                       ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            log.debug("learn save: %s", e)

    # ---------- навчання
    def step(self, now: float | None = None) -> dict:
        now = now or time.time()
        found = 0
        for tr in list(self.tr.tracks):
            srcs = set(tr.srcs)
            obs = [o for o in list(tr.obs) if not o.est]
            for a, b in zip(obs, obs[1:]):
                key = (tr.id, int(a.t), int(b.t))
                if key in self.seen:
                    continue
                dt, d = b.t - a.t, dist_km((a.x, a.y), (b.x, b.y))
                if dt < 240 or d < 12 or a.label == b.label:
                    continue
                v = d / dt * 3600
                base = self.base.get(tr.type)
                if not base or not (base * 0.35 < v < base * 2.2):
                    continue  # явний «телепорт» або стояння — не вимір
                self.seen[key] = 1
                if any(x[2] == a.label and x[3] == b.label and x[4] == int(b.t) for x in self.speeds[tr.type][-300:]):
                    continue  # той самий вимір уже записано (наприклад, до перезапуску)
                self.speeds[tr.type].append([round(v), tr.id, a.label, b.label, int(b.t)])
                self.speeds[tr.type] = self.speeds[tr.type][-300:]
                found += 1
            if tr.merged and ("m", tr.id) not in self.seen:
                self.seen[("m", tr.id)] = 1
                keep = next((x for x in self.tr.tracks if x.id == tr.merged), None)
                self.merges[f"{tr.type}->{keep.type if keep else '?'}"] += 1
                if keep and keep.type != tr.type:
                    for s in srcs - set(keep.srcs):
                        self.type_conf[s]["dup"] += 1
            elif not tr.merged and tr.closed and ("c", tr.id) not in self.seen and len(tr.srcs) >= 2:
                self.seen[("c", tr.id)] = 1
                for s in srcs:
                    self.type_conf[s]["ok"] += 1
        if len(self.seen) > 20000:
            self.seen = dict.fromkeys(list(self.seen)[-8000:], 1)  # лишаємо найновіші
        changed = self.apply_speeds()
        self.runs += 1
        self.last = now
        rec = {"t": int(now), "new_speed_samples": found, "speed_changes": changed}
        if found or changed:
            self.log.append(rec)
        self._save()
        return rec

    def apply_speeds(self) -> dict:
        """Медіана щонайменше 8 вимірів → номінальна швидкість типу (обмежено 0.6–1.5× паспортної)."""
        T = tracker_types()
        out = {}
        cur = self.tr.speed_over
        for typ, arr in self.speeds.items():
            if typ not in T or len(arr) < 8:
                continue
            med = statistics.median(x[0] for x in arr[-120:])
            base = self.base.get(typ, T[typ]["speed"])
            new = int(max(base * 0.6, min(base * 1.5, med)))
            old = cur.get(typ, base)
            if abs(new - old) >= 5:
                out[typ] = [old, new, len(arr)]
                cur[typ] = new  # лише живий трекер; глобальні TYPES (і мапа доби) не змінюються
        return out

    def state(self) -> dict:
        T = tracker_types()
        sp = {k: {"learned": self.tr.speed_over.get(k, self.base.get(k)), "passport": self.base.get(k), "samples": len(v),
                  "evidence": v[-5:]} for k, v in self.speeds.items()}
        tc = {s: {**c, "dup_rate": round(c["dup"] / max(1, c["dup"] + c["ok"]), 2)} for s, c in self.type_conf.items()
              if c["dup"] + c["ok"] >= 5}
        worst = dict(sorted(tc.items(), key=lambda kv: -kv[1]["dup_rate"])[:12])
        return {"runs": self.runs, "last": int(self.last), "speeds": sp, "merges": dict(self.merges),
                "type_reliability_worst": worst, "log": list(self.log)[-20:]}

    async def run(self, every: int = 300):
        await asyncio.sleep(60)
        while True:
            try:
                await asyncio.to_thread(self.step)
            except Exception as e:
                log.warning("learner: %s", e)
            await asyncio.sleep(every)


def tracker_types():
    from .tracker import TYPES
    return TYPES
