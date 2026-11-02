"""Статистика «мого району» (як архів Tzofar в Ізраїлі): скільки цілей проходило поруч з домом за останні доби,
о котрій годині найчастіше, з якого боку заходять і які типи. Джерело — мапи доби (data/daily/*.json), тобто ті самі
треки, що бачить користувач у «Мапі доби». Числа — треки трекера (оцінка: одна ціль іноді дає кілька треків)."""
from __future__ import annotations

import collections
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .geo import bearing, dist_km, to_xy

FROM = ["півночі", "північного сходу", "сходу", "південного сходу", "півдня", "південного заходу", "заходу", "північного заходу"]
_CACHE: dict[str, tuple[float, list]] = {}


def _kyiv_hour(ts: float) -> int:
    try:
        from zoneinfo import ZoneInfo
        return datetime.fromtimestamp(ts, ZoneInfo("Europe/Kyiv")).hour
    except Exception:  # noqa: BLE001
        return datetime.fromtimestamp(ts, timezone(timedelta(hours=2))).hour


def _load(folder: Path) -> list[tuple[str, list]]:
    out = []
    for f in sorted(folder.glob("????-??-??.json")):
        m = f.stat().st_mtime
        c = _CACHE.get(str(f))
        if not c or c[0] != m:
            try:
                tracks = json.loads(f.read_text(encoding="utf-8")).get("tracks") or []
            except Exception:  # noqa: BLE001
                tracks = []
            c = (m, tracks)
            _CACHE[str(f)] = c
        out.append((f.stem, c[1]))
    return out


def closest(pts: list, H) -> tuple[float, float, int] | None:
    """(відстань, момент, індекс сегмента) найближчого підходу треку [[lon, lat, t], …] до точки H (xy)."""
    best = None
    xy = [to_xy(p[1], p[0]) for p in pts]
    for i in range(len(xy)):
        a, ta = xy[i], pts[i][2]
        if i + 1 < len(xy):
            b, tb = xy[i + 1], pts[i + 1][2]
            vx, vy = b[0] - a[0], b[1] - a[1]
            L2 = vx * vx + vy * vy
            k = max(0.0, min(1.0, ((H[0] - a[0]) * vx + (H[1] - a[1]) * vy) / L2)) if L2 else 0.0
            q = (a[0] + vx * k, a[1] + vy * k)
            d, t = dist_km(H, q), ta + (tb - ta) * k
        else:
            d, t = dist_km(H, a), ta
        if best is None or d < best[0]:
            best = (d, t, i)
    return best


def area_stats(lat: float, lon: float, r_km: float = 25, days: int = 14, folder: Path | None = None) -> dict:
    from .daily import OUT
    folder = folder or OUT
    H = to_xy(lat, lon)
    hours = [0] * 24
    sides = collections.Counter()
    types = collections.Counter()
    per_day = []
    for day, tracks in _load(folder)[-days:]:
        n = 0
        for tr in tracks:
            pts = tr.get("pts") or []
            if not pts:
                continue
            c = closest(pts, H)
            if not c or c[0] > r_km:
                continue
            n += 1
            types[tr.get("type") or "?"] += 1
            hours[_kyiv_hour(c[1])] += 1
            # з якого боку зайшла: перша точка треку за 15–80 км від дому до найближчого підходу
            src = next((p for p in pts[:c[2] + 1] if 15 <= dist_km(H, to_xy(p[1], p[0])) <= 80), None)
            if src:
                sides[FROM[round(bearing(H, to_xy(src[1], src[0])) / 45) % 8]] += 1
        per_day.append({"day": day, "n": n})
    tot = sum(x["n"] for x in per_day)
    peak = sorted(range(24), key=lambda h: -hours[h])[:3] if tot else []
    return {"r_km": r_km, "days": len(per_day), "total": tot, "per_day": per_day, "hours": hours,
            "peak_hours": [h for h in peak if hours[h]], "sides": dict(sides.most_common()), "types": dict(types.most_common()),
            "avg_per_day": round(tot / len(per_day), 1) if per_day else 0}
