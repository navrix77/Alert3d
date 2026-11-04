"""Злиття напрямку з кількох джерел (пункт від каналів / навчений маршрут / рух між позиціями) з вагами з точності.

Вмикається САМ, лише коли журнал прогнозів (таблиця fcast) доводить виграш на днях, яких модель не бачила:
  - закритих пар усього ≥ 1000, на перевірці (останні 3 доби) ≥ 300;
  - медіана похибки злиття менша за показаний на мапі курс щонайменше на 2°;
  - частка влучань у ±45° не нижча;
  - те саме для шахедів окремо (якщо їх на перевірці ≥ 100).
Бектест 9 ночей (03.11): 258 пар, виграшу немає (21° проти 21–23°) — тому до накопичення даних вимкнено.
Результат кожної перевірки зберігається й показується на /api/fusion.
"""
from __future__ import annotations

import json
import math
import statistics
import time

SOURCES = ("ch", "ln", "mv")
MIN_TOTAL, MIN_TEST, MIN_GAIN = 1000, 300, 2.0


def ang(a: float, b: float) -> float:
    return abs((a - b + 540) % 360 - 180)


def kappa_for(p30: float) -> float:
    """Концентрація фон Мізеса, за якої P(|похибка| ≤ 30°) = p30."""
    best, err = 0.1, 9.0
    for k10 in range(1, 400):
        k = k10 / 10
        num = den = 0.0
        for i in range(360):
            th = -math.pi + 2 * math.pi * i / 360
            w = math.exp(k * math.cos(th))
            den += w
            if abs(th) <= math.radians(30):
                num += w
        if abs(num / den - p30) < err:
            best, err = k, abs(num / den - p30)
    return best


def fuse(cand: dict, kap: dict, typ: str) -> float | None:
    x = y = 0.0
    used = 0
    for s in SOURCES:
        k = kap.get(f"{typ}:{s}")
        if s in cand and k:
            r = math.radians(cand[s])
            x += k * math.sin(r)
            y += k * math.cos(r)
            used += 1
    if not used:
        return None
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _stats(errs: list[float]) -> dict:
    return {"n": len(errs), "med": round(statistics.median(errs), 1) if errs else None,
            "p45": round(sum(e <= 45 for e in errs) / len(errs), 3) if errs else None}


def evaluate(db, now: float | None = None) -> dict:
    """Навчання ваг на ранніх днях, перевірка на останніх 3 добах. Повертає звіт і рішення {on, kappa}."""
    now = now or time.time()
    try:
        rows = db.execute("SELECT t, type, cand, truth FROM fcast WHERE t > ? ORDER BY t", (now - 30 * 86400,)).fetchall()
    except Exception:  # noqa: BLE001 — таблиці ще немає
        rows = []
    days = sorted({int((t - 12 * 3600) // 86400) for t, *_ in rows})
    test_days = set(days[-3:])
    train = [(typ, json.loads(c), tr) for t, typ, c, tr in rows if int((t - 12 * 3600) // 86400) not in test_days]
    test = [(typ, json.loads(c), tr) for t, typ, c, tr in rows if int((t - 12 * 3600) // 86400) in test_days]
    kap: dict[str, float] = {}
    for typ in {r[0] for r in train}:
        for s in SOURCES:
            e = [ang(c[s], tr) for ty, c, tr in train if ty == typ and s in c]
            if len(e) >= 30:
                kap[f"{typ}:{s}"] = kappa_for(sum(x <= 30 for x in e) / len(e))
    rep: dict = {"at": int(now), "total": len(rows), "train": len(train), "test": len(test), "days": len(days), "kappa": kap, "by_type": {}}
    ok = len(rows) >= MIN_TOTAL and len(test) >= MIN_TEST and bool(kap)
    for typ in ["all"] + sorted({r[0] for r in test}):
        sub = [r for r in test if typ == "all" or r[0] == typ]
        cur = [ang(c["cur"], tr) for ty, c, tr in sub if "cur" in c]
        fu = []
        for ty, c, tr in sub:
            f = fuse(c, kap, ty)
            f = c.get("cur") if f is None else f
            if f is not None:
                fu.append(ang(f, tr))
        rep["by_type"][typ] = {"current": _stats(cur), "fused": _stats(fu)}
        if typ in ("all", "shahed") and (typ == "all" or len(sub) >= 100):
            a, b = _stats(cur), _stats(fu)
            if not (a["n"] and b["n"] and b["med"] <= a["med"] - MIN_GAIN and b["p45"] >= a["p45"]):
                ok = False
    rep["on"] = ok
    rep["why"] = ("злиття точніше на днях, яких модель не бачила" if ok else
                  f"замало даних ({len(rows)}/{MIN_TOTAL} пар, перевірка {len(test)}/{MIN_TEST})" if len(rows) < MIN_TOTAL or len(test) < MIN_TEST
                  else "виграшу немає: лишаємо поточний спосіб")
    return rep
