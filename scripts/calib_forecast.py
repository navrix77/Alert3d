"""Калібрування прогнозу «ціль в області за 30/60/120 хв» за історією знімків (brain.sqlite → hist).
Для кожного знімку рахуємо прогноз, а результат — чи з'явилась активна ціль в області у наступні h хвилин
(за наступними знімками). Групуємо прогнози в кошики й будуємо монотонну (ізотонічну) відповідність
«сирий p → спостережена частота». Пише data/fc_calib.json; прогноз застосовує її, коли в кошику ≥ MIN_N випадків.
Обмеження: результат — позиції цілей SKY (не незалежне джерело), тож це калібрування щодо власних треків.
Запуск: python scripts/calib_forecast.py data/brain.sqlite [data/fc_calib.json]"""
from __future__ import annotations

import bisect
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.forecast import HORIZONS, forecast  # noqa: E402
from app.geo import oblasts  # noqa: E402

EDGES = [0, .05, .1, .2, .3, .4, .5, .6, .7, .8, .9, .96, 1.01]
MIN_N = 30


def pava(xs: list[tuple[float, float, int]]) -> list[tuple[float, float, int]]:
    """Ізотонічна регресія (pool adjacent violators) над кошиками (середній p, частота, n)."""
    out = []
    for x, y, n in xs:
        out.append([x * n, y * n, n])
        while len(out) > 1 and out[-2][1] / out[-2][2] > out[-1][1] / out[-1][2]:
            a, b = out.pop(), out.pop()
            out.append([a[0] + b[0], a[1] + b[1], a[2] + b[2]])
    return [(x / n, y / n, n) for x, y, n in out]


def main(db: str, outp: str) -> dict:
    d = sqlite3.connect(db)
    snaps = [(t, json.loads(j)) for t, j in d.execute("SELECT t, j FROM hist ORDER BY t")]
    O = oblasts()
    present = []  # (t, множина областей з активною ціллю)
    for t, s in snaps:
        present.append((t, {O.of(tr["lon"], tr["lat"]) for tr in s.get("tracks", []) if tr.get("lat") is not None} - {None}))
    ts = [t for t, _ in present]
    pairs = {h: [] for h in HORIZONS}
    for i, (t, s) in enumerate(snaps):
        if t > ts[-1] - max(HORIZONS) * 60:
            break
        tracks = [dict(tr, status="active") for tr in s.get("tracks", []) if tr.get("lat") is not None]
        fc = forecast({"tracks": tracks, "now": t}, [], None, None)["oblasts"]
        for h in HORIZONS:
            j = bisect.bisect_right(ts, t + h * 60)
            seen = set().union(*(present[k][1] for k in range(i + 1, j))) if j > i + 1 else set()
            for name, v in fc.items():
                if name in present[i][1]:
                    continue  # ціль уже в області — прогноз тривіальний, не калібруємо ним
                pairs[h].append((v.get(f"raw{h}", v[f"p{h}"]), 1.0 if name in seen else 0.0))
    res = {"n_snapshots": len(snaps), "span_h": round((ts[-1] - ts[0]) / 3600, 1) if ts else 0, "horizons": {}}
    for h, pr in pairs.items():
        bins = []
        for a, b in zip(EDGES, EDGES[1:]):
            sel = [y for p, y in pr if a <= p < b]
            ps = [p for p, y in pr if a <= p < b]
            if sel:
                bins.append((sum(ps) / len(ps), sum(sel) / len(sel), len(sel)))
        iso = pava(bins)
        res["horizons"][str(h)] = {"bins": [[round(x, 3), round(y, 3), n] for x, y, n in bins],
                                   "map": [[round(x, 3), round(y, 3), n] for x, y, n in iso if n >= MIN_N], "pairs": len(pr)}
    Path(outp).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


if __name__ == "__main__":
    r = main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else str(Path(__file__).resolve().parent.parent / "data" / "fc_calib.json"))
    for h, v in r["horizons"].items():
        print(h, "pairs", v["pairs"], "bins (p_сирий, частота, n):", v["bins"])
