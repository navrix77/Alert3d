"""Єдиний підрахунок цілей (04.11, власник: «головне реальні цілі»).

Чому не «кількість треків» і не «сума ×N»: канали пишуть про місця, де щось побачили, а не про кількість. Одну ціль описує кілька
повідомлень, і трекер обережно не склеює їх у масованих нальотах, тому за ніч створюється в 2-4 рази більше треків, ніж цілей.
Бектест проти офіційних підсумків Повітряних сил (збито/подавлено за 6 ночей) це показав: треків 180-1341 проти 71-371.

Метод: мінімальне покриття траєкторіями. Два фрагменти — одна ціль, якщо другий починається після кінця першого й туди можна
долетіти за швидкістю типу з допуском похибки позиції. Мінімум ланцюгів, що пояснюють усі повідомлення, — це нижня межа
(одночасно в різних місцях — гарантовано різні цілі). Верхня межа — фрагменти, що мають бодай два повідомлення, без склейки.
Точне число з повідомлень каналів не отримати; тут оцінка з діапазоном, а не точна цифра.
"""
from __future__ import annotations

import math
from collections import Counter

SPEED = {"uav": 170, "shahed": 170, "jet": 450, "molniya": 120, "geran5": 550, "cruise": 800, "banderol": 700, "ballistic": 2000, "kab": 400,
         "rszv": 1500, "recon": 110, "lancet": 95, "fpv": 80, "fpvf": 60}
# час життя цілі в лічильнику «зараз у повітрі», хв: той самий, що й показ на мапі (SHOW у web/app.js)
LIVE_MIN = {"uav": 25, "shahed": 25, "molniya": 20, "jet": 6, "cruise": 2, "ballistic": 1, "banderol": 2, "geran5": 5, "rszv": 1,
            "recon": 15, "lancet": 10, "fpv": 5, "fpvf": 5, "kab": 5}
# параметри з бектесту (6 ночей): допуск похибки позиції, км, і найбільший розрив між фрагментами, с
TOL_KM, GAP_S = 10.0, 2700
TOL_LOW_KM, GAP_LOW_S = 20.0, 3600


def _dkm(a, b) -> float:
    return math.hypot((a[0] - b[0]) * 111.0, (a[1] - b[1]) * 111.0 * math.cos(math.radians((a[0] + b[0]) / 2)))


def chains(frags: list[dict], tol_km: float, gap_s: float) -> int:
    """frags: {type, t0, t1, p0:(lat,lon), p1:(lat,lon)}. Повертає мінімальну кількість ланцюгів (Хопкрофт-Карп спрощено)."""
    fr = sorted(frags, key=lambda f: f["t0"])
    n = len(fr)
    adj: list[list[int]] = [[] for _ in range(n)]
    for i, a in enumerate(fr):
        sp = SPEED.get(a["type"], 170)
        for j in range(i + 1, n):
            b = fr[j]
            gap = b["t0"] - a["t1"]
            if gap > gap_s:
                break  # фрагменти відсортовані за початком, далі розрив лише більший
            if b["type"] != a["type"] or gap < -60:
                continue
            if _dkm(a["p1"], b["p0"]) <= sp * max(gap, 0) / 3600 + tol_km:
                adj[i].append(j)
    match = [-1] * n

    def aug(u: int, seen: set) -> bool:
        stack = [(u, iter(adj[u]))]
        path: list[tuple[int, int]] = []
        while stack:
            node, it = stack[-1]
            for v in it:
                if v in seen:
                    continue
                seen.add(v)
                if match[v] < 0:
                    path.append((node, v))
                    for x, y in path:
                        match[y] = x
                    return True
                path.append((node, v))
                stack.append((match[v], iter(adj[match[v]])))
                break
            else:
                stack.pop()
                if path:
                    path.pop()
        return False

    m = sum(1 for u in range(n) if aug(u, set()))
    return n - m


def estimate(frags: list[dict]) -> dict:
    """Діапазон кількості різних цілей за період: low (мінімальне покриття), mid (рекомендована оцінка), high (фрагменти з ≥2 повідомленнями).
    По типах і загалом."""
    by: dict[str, list[dict]] = {}
    for f in frags:
        by.setdefault(f["type"], []).append(f)
    out: dict[str, dict] = {}
    for t, fs in by.items():
        low = chains(fs, TOL_LOW_KM, GAP_LOW_S)
        mid = max(low, chains(fs, TOL_KM, GAP_S))
        high = max(mid, sum(1 for f in fs if f.get("pubs", 2) >= 2))
        out[t] = {"low": low, "mid": mid, "high": high}
    tot = {k: sum(v[k] for v in out.values()) for k in ("low", "mid", "high")} if out else {"low": 0, "mid": 0, "high": 0}
    return {"total": tot, "by_type": out}


def live(tracks: list[dict], now: float, snap_now: float | None = None) -> dict:
    """Скільки цілей зараз у повітрі за повідомленнями каналів: треки, активні й свіжі за часом життя свого типу
    (як на мапі). «×N» не додається, а лишається окремо як верхня межа одиниць."""
    drift = max(0.0, now - (snap_now or now))
    by: Counter = Counter()
    units: Counter = Counter()
    for t in tracks:
        if t.get("status") != "active":
            continue
        age = ((t.get("ev") or {}).get("age") or 0) + drift
        if age >= LIVE_MIN.get(t.get("type"), 10) * 60:
            continue
        by[t["type"]] += 1
        units[t["type"]] += t.get("count") or 1
    return {"total": sum(by.values()), "by_type": dict(by), "units_max": sum(units.values())}
