"""Лабораторія трекінгу (12.11): чесне порівняння алгоритмів на реальному журналі без ідентифікаторів цілей.

Метрика «несподіванка»: щойно канал уперше називає пункт X для цілі («над X» або «курсом на X»), дивимось, наскільки
близько до X алгоритм УЖЕ показував (або вів туди протягом найближчих хвилин) ціль тієї ж родини ДО цього повідомлення.
  p-подія («над/біля X»):   мін. відстань від X до показаних цілей у момент t
  t-подія («курсом на X»):  мін. відстань від X до показаних цілей у моменти t, t+4, t+8 хв (без нових даних)
Менше — краще. Поруч рахуємо середню кількість активних цілей (щоб алгоритм не «вигравав», засіявши мапу привидами).
Відлуння (той самий пункт тієї ж родини за останні 4 хв від будь-якого каналу) не оцінюємо.

    python3 scripts/flow_lab.py data/night/journal.json [--from UNIX] [--algo base,flow]
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import statistics
import sys
import time as _time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("PYTEST_CURRENT_TEST", "flowlab")

from app.config import SOURCES  # noqa: E402
from app.geo import dist_km, to_xy  # noqa: E402
from app.tracker import Tracker  # noqa: E402
from scripts.backtest import Feeder, load  # noqa: E402

FAMILY = {"jet": "drone", "shahed": "drone", "uav": "drone", "geran5": "drone", "molniya": "near", "fpv": "near", "fpvf": "near",
          "lancet": "near", "recon": "near", "banderol": "missile", "cruise": "missile", "ballistic": "bal", "rszv": "bal"}
ECHO_S = 240
LOOK = (0, 240, 480)


class BaseAlgo:
    """Поточний трекер SKY: позиції з snapshot (те, що бачить користувач)."""
    name = "base"

    def __init__(self):
        self.trk = Tracker(SOURCES, learn=False)

    def ingest(self, obs, src, t, link):
        return Tracker.ingest(self.trk, obs, src, t, link)

    def shown(self, now, future=False):
        out = []
        trk = self.trk
        if future:  # snapshot змінює стан (закриває/прибирає цілі) — у майбутнє дивимось на копії
            import copy
            ing = trk.__dict__.pop("ingest", None)
            try:
                trk = copy.deepcopy(self.trk)
            finally:
                if ing:
                    self.trk.ingest = ing
        for x in trk.snapshot(now)["tracks"]:
            if x["status"] == "active":
                out.append((FAMILY.get(x["type"]), to_xy(x["lat"], x["lon"])))
        return out


def run(path, algos, t_from=None, verbose=False):
    if os.path.isdir(path):  # архів по днях (гілка night-data, archive/*.json.gz — scripts/journal_archive.py)
        import glob
        rows = sorted((r for f in sorted(glob.glob(os.path.join(path, "*.json.gz"))) for r in load(f)), key=lambda r: r[0])
    else:
        rows = sorted(load(path), key=lambda r: r[0])
    base = next((a for a in algos if a.name == "base"), None) or BaseAlgo()
    feeder = Feeder(base.trk)
    others = [a for a in algos if a.name != "base"]
    use_base = any(a.name == "base" for a in algos)
    seen: dict = {}
    res = {a.name: collections.defaultdict(list) for a in algos}
    act = {a.name: [] for a in algos}
    n_ev = 0

    def hook(obs, src, t=None, link=None, _split=False):
        nonlocal n_ev
        if _split:
            return Tracker.ingest(base.trk, obs, src, t, link, _split=True)
        fam = FAMILY.get(obs.type)
        if obs.kind == "track" and fam and (t_from is None or t >= t_from):
            for r in obs.places:
                if r.role not in ("p", "t"):
                    continue
                key = (fam, r.place.name, round(r.place.lat, 2))
                fresh = t - seen.get(key, -1e9) > ECHO_S
                seen[key] = t
                if not fresh:
                    continue
                n_ev += 1
                for a in algos:
                    best = 1e9
                    for dt in ((0,) if r.role == "p" else LOOK):
                        sh = a.shown(t - 1, False) if dt == 0 else a.shown(t + dt, True)
                        if dt == 0:
                            act[a.name].append(len(sh))
                        for f2, xy in sh:
                            if f2 == fam:
                                best = min(best, dist_km(xy, r.place.xy))
                    res[a.name][(fam, r.role)].append(best)
                    res[a.name][("ALL", r.role)].append(best)
        elif obs.kind == "track" and fam:
            for r in obs.places:
                seen[(fam, r.place.name, round(r.place.lat, 2))] = t
        for a in others:
            try:
                a.ingest(obs, src, t, link)
            except Exception as e:  # noqa: BLE001
                if verbose:
                    print("ERR", a.name, e)
                raise
        return Tracker.ingest(base.trk, obs, src, t, link)

    base.trk.ingest = hook
    t0 = _time.time()
    for t, src, link, kind, typ, pl, track, text in rows:
        if text:
            feeder.feed(text, src, t, link)
    out = {}
    for a in algos:
        o = {}
        for k, v in sorted(res[a.name].items()):
            v2 = [min(x, 999) for x in v]
            o[f"{k[0]}:{k[1]}"] = {"n": len(v2), "med": round(statistics.median(v2), 1), "le10": round(sum(x <= 10 for x in v2) / len(v2), 3),
                                   "le25": round(sum(x <= 25 for x in v2) / len(v2), 3), "miss": round(sum(x > 60 for x in v2) / len(v2), 3)}
        o["active_mean"] = round(statistics.mean(act[a.name]), 1) if act[a.name] else 0
        out[a.name] = o
    out["_events"] = n_ev
    out["_sec"] = round(_time.time() - t0, 1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--from", dest="t_from", type=float)
    ap.add_argument("--algo", default="base,flow")
    ap.add_argument("--json")
    a = ap.parse_args()
    algos = []
    for n in a.algo.split(","):
        if n == "base":
            algos.append(BaseAlgo())
        elif n == "flow":
            from app.flow import FlowAlgo
            algos.append(FlowAlgo())
    out = run(a.src, algos, a.t_from)
    for n, o in out.items():
        if n.startswith("_"):
            print(n, o)
            continue
        print(f"== {n}  (активних у середньому: {o['active_mean']})")
        for k, v in o.items():
            if k != "active_mean":
                print(f"  {k:12s} n={v['n']:5d}  медіана={v['med']:6.1f} км  ≤10км={v['le10']:.0%}  ≤25км={v['le25']:.0%}  промах>60км={v['miss']:.0%}")
    if a.json:
        Path(a.json).write_text(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
