"""Ядро тренінгу (07.11): окремий процес, що щоночі відтворює журнал, перевіряє кандидати параметрів на «чужій» добі
і публікує data/params.json лише там, де похибка прогнозу реально впала. Застосунок підхоплює файл на льоту; погіршення неможливе:
кандидат ухвалюється, лише коли медіанна похибка на ≥5% менша й вибірка ≥20.

    python -m app.trainer [шлях до brain.sqlite | journal.json(.gz)]
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

DIR = Path(os.getenv("PERSIST_DIR") or Path(__file__).resolve().parent.parent / "data")
PARAMS = DIR / "params.json"
SCALES = (0.85, 1.0, 1.15)  # множники паспортної швидкості для кандидатів
MIN_N, MIN_GAIN = 20, 0.05


def load_params() -> dict:
    try:
        return json.loads(PARAMS.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _score(rep: dict, typ: str) -> tuple[float, int]:
    """Медіана похибки прогнозу «як на мапі» (route) за горизонтами для типу, зважена вибіркою."""
    tot, n = 0.0, 0
    for _h, v in ((rep.get(typ) or {}).get("route") or {}).items():
        tot += v["med"] * v["n"]
        n += v["n"]
    return (tot / n if n else float("inf")), n


def train(rows: list, test_from: float | None = None) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import backtest as bt
    from app.tracker import TYPES
    base = bt.run(rows, test_from, methods={"route": bt.m_route}, verbose=False)
    cands = {s: bt.run(rows, test_from, methods={"route": bt.m_route}, verbose=False,
                       speed_over={t: TYPES[t]["speed"] * s for t in TYPES}) for s in SCALES if s != 1.0}
    speeds, report = {}, {}
    for typ in TYPES:
        b, nb = _score(base, typ)
        best, bs = 1.0, b
        for s, rep in cands.items():
            sc, n = _score(rep, typ)
            if n >= MIN_N and sc < bs * (1 - MIN_GAIN):
                best, bs = s, sc
        report[typ] = {"n": nb, "base_km": None if b == float("inf") else round(b, 1), "best_scale": best,
                       "best_km": None if bs == float("inf") else round(bs, 1)}
        if best != 1.0 and nb >= MIN_N:
            speeds[typ] = round(TYPES[typ]["speed"] * best, 1)
    return {"version": int(time.time()), "speed_over": speeds, "report": report,
            "heading": base.get("_heading_err"), "test_rows": len(rows)}


def main(argv: list[str]) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import backtest as bt
    src = argv[1] if len(argv) > 1 else str(DIR / "brain.sqlite")
    rows = bt.load(src)
    if len(rows) < 500:
        print("замало журналу для тренінгу:", len(rows))
        return 0
    out = train(rows)
    old = load_params()
    PARAMS.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("тренінг завершено: змінено швидкостей:", out["speed_over"], "| було:", old.get("speed_over"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
