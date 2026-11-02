"""Прогноз «що буде далі»: ймовірність, що ціль зайде в область протягом 30/60/120 хв.

Чесна евристика, не магія:
- кожна активна ціль «пускає» віяло можливих траєкторій (названий маршрут, далі, курс ±30°), з урахуванням
  довіри до цілі й того, що ціль може зникнути (збиття/посадка), експоненційне «виживання»;
- пуски, по яких ще не всі цілі видно, дають віяло від місця пуску в бік України
  (або в бік місць, куди такі цілі заходили раніше, навчання);
- P(область) = 1 − Π(1 − pᵢ) по всіх променях.
"""
from __future__ import annotations

import math

from .geo import bearing, dist_km, from_xy, move, oblasts, to_xy

FAN = [(-30, 0.1), (-15, 0.2), (0, 0.4), (15, 0.2), (30, 0.1)]
HORIZONS = (30, 60, 120)
SURVIVE_MIN = 70.0  # характерний «час життя» цілі в повітрі, хв


def _rays(start, heading, route_xy, speed, horizon=120, step=5):
    """Точки променів: [(вага, [(хв, x, y), ...]), ...]."""
    out = []
    for dh, w in FAN if heading is not None else [(a, 1 / 8) for a in range(0, 360, 45)]:
        pts, p, t = [], start, 0.0
        path = list(route_xy)
        hd = (heading + dh) % 360 if heading is not None else dh
        while t < horizon:
            km = speed * step / 60
            if path:
                tgt = path[0]
                d = dist_km(p, tgt)
                if d <= km:
                    p = tgt
                    path.pop(0)
                    if path:
                        hd = bearing(p, path[0])
                else:
                    hd0 = bearing(p, tgt)
                    p = move(p, hd0, km)
                    hd = hd0
            else:
                p = move(p, hd, km)
            t += step
            pts.append((t, p[0], p[1]))
        out.append((w, pts))
    return out


def forecast(snap: dict, launches: list[dict], brain=None, gaz=None) -> dict:
    obl = oblasts()
    acc: dict[str, dict[int, float]] = {}  # область -> горизонт -> Π(1-p) по НЕЗАЛЕЖНИХ цілях
    exp_n: dict[str, dict[int, float]] = {}  # очікувана кількість цілей

    def fan(start, heading, route_xy, speed, conf, count=1):
        """Промені віяла, АЛЬТЕРНАТИВИ однієї цілі (вона полетить лише одним із них), тож їхні ваги додаються,
        а між різними цілями ймовірності поєднуються як незалежні. Так прогноз не «насичується» до 100%."""
        per: dict[str, dict[int, float]] = {}
        for w, pts in _rays(start, heading, route_xy, speed):
            seen = set()
            for t, x, y in pts:
                la, lo = from_xy(x, y)
                o = obl.of(lo, la)
                if o and o not in seen:
                    seen.add(o)
                    surv = math.exp(-t / SURVIVE_MIN)
                    row = per.setdefault(o, {h: 0.0 for h in HORIZONS})
                    for h in HORIZONS:
                        if t <= h:
                            row[h] += w * surv
        for o, row in per.items():
            A = acc.setdefault(o, {h: 1.0 for h in HORIZONS})
            E = exp_n.setdefault(o, {h: 0.0 for h in HORIZONS})
            for h in HORIZONS:
                q = min(0.9, row[h]) * conf          # одна ціль
                A[h] *= (1 - q) ** max(1, count)     # група з count цілей
                E[h] += q * max(1, count)

    linked: dict[str, int] = {}
    for tr in snap.get("tracks", []):
        if tr.get("status") != "active":
            continue
        start = to_xy(tr["lat"], tr["lon"])
        route = [to_xy(la, lo) for lo, la in tr.get("route") or []]
        fan(start, tr.get("hd"), route, tr.get("speed") or 170, tr.get("conf", 0.5), min(6, tr.get("count") or 1))
        L = tr.get("launch")
        if L and not L.get("est") and L.get("id"):
            linked[L["id"]] = linked.get(L["id"], 0) + (tr.get("count") or 1)

    # пуски, по яких ще не всі цілі видно на карті
    for L in launches:
        if snap.get("now", 0) - L["t"] > 3 * 3600:
            continue
        n = (L.get("count") or 3) - linked.get(L["id"], 0)
        if n <= 0:
            continue
        site = to_xy(L["lat"], L["lon"])
        speed = {"shahed": 170, "jet": 450, "cruise": 750, "ballistic": 2000}.get(L.get("type") or "shahed", 170)
        heads = []
        if gaz is not None and brain is not None:
            # куди такі цілі з цього місця заходили раніше (навчання ланцюжка пуску)
            st = brain.site_stats(L.get("type") or "shahed", None)
            for entry, c in sorted(st.items(), key=lambda kv: -kv[1])[:3]:
                pass
        target = to_xy(49.0, 31.5)  # центр України — якщо досвіду ще немає
        heads = heads or [bearing(site, target)]
        for hd in heads:
            fan(site, hd, [], speed, 0.5, min(6, n))

    out = {}
    for name, row in acc.items():
        out[name] = {f"p{h}": round(1 - row[h], 2) for h in HORIZONS}
        out[name].update({f"n{h}": round(exp_n[name][h], 1) for h in HORIZONS})
    top = sorted(out.items(), key=lambda kv: -kv[1]["p60"])
    return {"oblasts": dict(top), "model": "fan-v2"}
