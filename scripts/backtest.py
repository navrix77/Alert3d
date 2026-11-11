"""Бектест прогнозу траєкторій на журналі повідомлень (brain.sqlite → msg або JSON-вивантаження).

Чесна перевірка без «підглядання в майбутнє»: журнал відтворюється в часі, навчання маршрутів іде онлайн
(модель знає лише те, що було ДО моменту прогнозу). У момент кожної названої каналом позиції цілі робимо
прогноз на +10/+20/+30 хв кількома методами й порівнюємо з тим, де ціль реально назвали потім.

    python scripts/backtest.py data/brain.sqlite            # уся історія, тест — остання доба
    python scripts/backtest.py msgs.json --test-from 1793516400 --json report.json
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import os
import re
import sqlite3
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("PYTEST_CURRENT_TEST", "backtest")  # аудит не пише у файл

from app import parser as parser_mod  # noqa: E402
from app.brain import Brain  # noqa: E402
from app.config import SOURCES  # noqa: E402
from app.geo import bearing, dist_km, move  # noqa: E402
from app.tracker import MAP_K, SHOW_BY_TYPE, SHOW_MIN, TYPES, Tracker, along, map_xy  # noqa: E402

HORIZONS = (10, 20, 30)


def load(path: str) -> list[tuple]:
    if path.endswith(".json.gz"):  # вивантаження сервера з гілки ops-data (journal-72h.json.gz)
        import gzip
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return [tuple(r) for r in json.load(f)]
    if path.endswith(".json"):
        return [tuple(r) for r in json.loads(Path(path).read_text(encoding="utf-8"))]
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    return db.execute("SELECT t, src, link, kind, type, places, track, text FROM msg ORDER BY t").fetchall()


class Feeder:
    """Спрощена копія main.feed: сегменти, контекст каналу, тип із заголовка."""

    def __init__(self, trk: Tracker) -> None:
        self.p = parser_mod.Parser()
        self.trk = trk
        self.ctx: dict[str, tuple] = {}

    def feed(self, text: str, src: str, ts: float, link) -> list[str]:
        p, trk = self.p, self.trk
        segs = p.segments(text)
        prev = self.ctx.get(src)
        pctx = (prev[1], prev[2]) if prev and 0 <= ts - prev[0] < 1800 else None
        whole = p.parse(text, src, pctx)
        ctx = pctx
        if whole.places:
            la = sum(r.place.lat for r in whole.places) / len(whole.places)
            lo = sum(r.place.lon for r in whole.places) / len(whole.places)
            ctx = (la, lo)
            self.ctx[src] = (ts, la, lo)
        msg_type = whole.type if len(segs) > 1 else None
        if len(segs) > 1 and parser_mod.AFTERMATH.search(text.lower()):
            msg_type = None
            segs = [s for s in segs if not parser_mod.AFTERMATH.search(s.lower())]
        trk.exclude = set()
        touched = []
        fc_msg = parser_mod.forecast(parser_mod.norm(text)) or parser_mod.past_strike(parser_mod.norm(text))  # як у main.feed: прогноз на ніч — не цілі
        for seg in segs:
            o = p.parse(seg, src, ctx)
            if fc_msg and not parser_mod.LIVE.search(parser_mod.norm(seg)):
                o.type, o.no_target, o.close = None, True, False
            if o.type is None and msg_type and o.places and not o.close and not o.no_target and len(segs) > 1:
                o.type = msg_type
            if o.kind in ("track", "zone", "close", "filtered", "avia"):
                o.raw = seg
                rec = trk.ingest(o, src, ts, link)
                if rec.get("track") and o.kind == "track":
                    touched.append(rec["track"])
                    if len(segs) > 1:
                        trk.exclude.add(rec["track"])
        trk.exclude = set()
        return touched


# ---------------- методи прогнозу: (трек, brain, хвилини) → xy
def m_stay(tr, brain, h):
    return (tr.last.x, tr.last.y)


def m_dr(tr, brain, h):
    if tr.heading is None:
        return (tr.last.x, tr.last.y)
    return move((tr.last.x, tr.last.y), tr.heading, tr.speed * h / 60)


def m_route(tr, brain, h):
    """Як показує карта: уздовж названого каналами маршруту, далі — тим самим курсом."""
    km = tr.speed * h / 60
    if tr.route:
        pts = tr.path()
        tot = sum(dist_km(pts[i - 1], pts[i]) for i in range(1, len(pts)))
        if km <= tot:
            return along(pts, km)
        hd = bearing(pts[-2], pts[-1]) if len(pts) > 1 else tr.heading
        return move(pts[-1], hd, km - tot) if hd is not None else pts[-1]
    return m_dr(tr, brain, h)


def m_learned(tr, brain, h):
    """Навчений ланцюжок пунктів (brain.next_path); без нього — як m_route."""
    if tr.route or not brain or not tr.last.place:
        return m_route(tr, brain, h)
    from app.geo import from_xy, to_xy
    la, lo = from_xy(tr.last.x, tr.last.y)
    chain = brain.next_path(tr.type, tr.last.place.name, tr.heading, (la, lo), steps=4)
    if not chain:
        return m_dr(tr, brain, h)
    pts = [(tr.last.x, tr.last.y)] + [to_xy(c[2], c[3]) for c in chain]
    km = tr.speed * h / 60
    tot = sum(dist_km(pts[i - 1], pts[i]) for i in range(1, len(pts)))
    if km <= tot:
        return along(pts, km)
    return move(pts[-1], bearing(pts[-2], pts[-1]), km - tot)


def m_map(tr, brain, h):
    """Як мапа SKY показує ціль зараз: модель зміщення map_disp (MAP_K/MAP_POW) і ліміт показу SHOW_BY_TYPE
    (Track.est(mapm=True)), а не паспортна швидкість, як у dr/route/learned."""
    return map_xy(tr, tr.last.t + h * 60, brain)


def m_map0(tr, brain, h):
    """Мапа до 11.11: без маршруту — прямо за курсом (для порівняння)."""
    return tr.est(tr.last.t + h * 60, SHOW_BY_TYPE.get(tr.type, SHOW_MIN), MAP_K.get(tr.type, 1.0), mapm=True)


METHODS = {"stay": m_stay, "dr": m_dr, "route": m_route, "learned": m_learned, "map": m_map, "map0": m_map0}


def truth_at(obs, t):
    """Де ціль насправді була в момент t: інтерполяція між названими позиціями (проміжок ≤ 20 хв)."""
    real = [o for o in obs if not o.est]
    for a, b in zip(real, real[1:]):
        if a.t <= t <= b.t and b.t - a.t <= 1200:
            k = (t - a.t) / max(1.0, b.t - a.t)
            return (a.x + (b.x - a.x) * k, a.y + (b.y - a.y) * k)
    near = [o for o in real if abs(o.t - t) <= 180]
    return (near[0].x, near[0].y) if near else None


def run(rows, test_from: float | None = None, methods=None, verbose=True, speed_over: dict | None = None,
        samples: list | None = None, dedup: bool = False) -> dict:
    """samples (якщо передано): сюди дописуються сирі зразки (t0, тип, хв, метод, похибка км) для власних розрізів.
    dedup: один зразок на (трек, позиція ±5 км, наступна позиція-істина): копії того самого поста іншими каналами за секунди
    (alarmua, shahedradar, trevogaa_radar…) не рахуються окремими прогнозами (журнал 09.11: 4 із 7 зразків «без маршруту»
    були однією ціллю)."""
    methods = methods or METHODS
    brain = Brain(Path(":memory:"))
    trk = Tracker(SOURCES, brain, learn=True)
    if speed_over:
        trk.speed_over.update(speed_over)  # кандидат тренажера (app/trainer.py)
    fd = Feeder(trk)
    test_from = test_from or (rows[-1][0] - 86400)
    pending = []  # (track_obj, t0, type, {(метод, h): xy}, has_route)
    seen = set()
    last_snap = 0.0
    for t, src, link, kind, typ, pl, track, text in rows:
        if not text or (src, link, text) in seen:
            continue
        seen.add((src, link, text))
        if t - last_snap >= 60:  # як живий сервер: знімок щохвилини виставляє навчений прогноз (і його самоперевірку)
            trk.snapshot(t)
            last_snap = t
        for tid in fd.feed(text, src, t, link):
            tr = next((x for x in trk.tracks if x.id == tid), None)
            if not tr or tr.last.est or tr.last.t != t or t < test_from or tr.type not in TYPES:
                continue
            if pending and pending[-1][0] is tr and pending[-1][1] == t:
                continue
            import copy
            snap = copy.copy(tr)  # стан треку в момент прогнозу (маршрут/курс/швидкість зміняться потім)
            snap.route, snap.obs = list(tr.route), list(tr.obs)
            pending.append((tr, t, tr.type, snap, bool(tr.route)))
    # істина — НАСТУПНА названа позиція, що відрізняється від поточної (> 5 км), через 3–40 хв:
    # повтори того самого пункту (підтвердження іншими каналами) прогнозом не перевіряються
    err = collections.defaultdict(list)
    angs = collections.defaultdict(list)
    used = set()
    for tr, t0, typ, snap, has_route in pending:
        if tr.merged:
            continue
        p0 = (snap.last.x, snap.last.y)
        nxt = next((o for o in tr.obs if not o.est and 180 <= o.t - t0 <= 2400 and dist_km(p0, (o.x, o.y)) > 5), None)
        if nxt is None:
            continue
        if dedup:
            key = (id(tr), round(p0[0] / 5), round(p0[1] / 5), nxt.t)  # та сама позиція (±5 км) і та сама істина
            if key in used:
                continue
            used.add(key)
        h = (nxt.t - t0) / 60
        b = "≤10хв" if h <= 10 else ("≤20хв" if h <= 20 else "≤40хв")
        truth = (nxt.x, nxt.y)
        for m, f in methods.items():
            e = dist_km(f(snap, brain, h), truth)
            if samples is not None:
                samples.append((t0, typ, h, m, e))
            for g in (typ, "ALL", "route" if has_route else "noroute"):
                err[(g, m, b)].append(e)
        hd = snap.heading
        if snap.route:
            hd = bearing(p0, snap.route[0].xy)
        if hd is not None:
            d = abs((bearing(p0, truth) - hd + 540) % 360 - 180)
            for g in (typ, "ALL", "route" if has_route else "noroute"):
                angs[g].append(d)
    rep = {"_heading_err": {g: {"n": len(v), "med": round(statistics.median(v)), "le45": round(sum(x <= 45 for x in v) / len(v), 2)} for g, v in angs.items()}}
    for (g, m, h), es in sorted(err.items()):
        rep.setdefault(g, {}).setdefault(m, {})[h] = {
            "n": len(es), "med": round(statistics.median(es), 1), "p15": round(sum(e <= 15 for e in es) / len(es), 2)}
    rep["_live_pred_acc"] = brain.pred_acc()
    rep["_live_hd_acc"] = brain.hd_acc() if hasattr(brain, "hd_acc") else {}
    if verbose:
        print("Живa метрика прогнозу «ймовірно далі» (v2) за весь повтор:", rep["_live_pred_acc"])
        print("Похибка курсу (град.):", rep["_heading_err"])
        print("Жива самоперевірка напрямку (≤45°):", rep["_live_hd_acc"])
        for g in rep:
            if g.startswith("_"):
                continue
            print(f"\n== {g}")
            for m in methods:
                if m in rep[g]:
                    print(f"  {m:8}", "  ".join(f"{h}: n={v['n']:4} мед={v['med']:5}км ≤15км={v['p15']:.0%}" for h, v in sorted(rep[g][m].items())))
    return rep


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--test-from", type=float)
    ap.add_argument("--json")
    ap.add_argument("--dedup", action="store_true", help="один зразок на (трек, позицію-істину)")
    a = ap.parse_args()
    r = run(load(a.src), a.test_from, dedup=a.dedup)
    if a.json:
        Path(a.json).write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
