"""Виміряна частка помилкових прив'язок на відкладеній вибірці tests/geo_holdout.json (не для підлаштування правил).
Помилка: місце потрапило в область, якої в повідомленні не мається на увазі (або в сусідню через тезку).
Пропуск: місце є, а SKY не знайшов жодного. Зайве: місць немає, а SKY щось поставив.
Запуск: python scripts/geo_eval.py [--json] [--show]"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def run(show: bool = False) -> dict:
    from app.geo import oblasts
    from app.parser import Parser
    O = oblasts()
    cases = json.loads((ROOT / "tests" / "geo_holdout.json").read_text(encoding="utf-8"))["cases"]
    wrong, missed, spur, placed, total_places = [], [], [], 0, 0
    gaz = Parser().gaz
    for c in cases:
        p = Parser(gaz)  # окремий екземпляр: без контексту попередніх повідомлень
        o = p.parse(c["text"], c["src"])
        exp = set(c["oblasts"]) | ({"Київ"} if "Київська" in c["oblasts"] else set())
        got = [(r.place.name, O.of(r.place.lon, r.place.lat)) for r in o.places]
        total_places += len(got)
        if not exp:
            if got:
                spur.append((c["text"], got))
            continue
        if not got:
            missed.append(c["text"])
            continue
        placed += 1
        def near_exp(name, lon, lat):  # пункт біля межі (≤ ~15 км) очікуваної області — не помилка тезки
            return any(O.of(lon + dx, lat + dy) in exp for dx in (-0.2, 0, 0.2) for dy in (-0.13, 0, 0.13))
        bad = [(n, ob) for (n, ob), r in zip(got, o.places) if ob and ob not in exp and not near_exp(n, r.place.lon, r.place.lat)]
        if bad:
            wrong.append((c["text"], bad, sorted(exp)))
    n_exp = sum(1 for c in cases if c["oblasts"])
    res = {"cases": len(cases), "with_places": n_exp, "placed": placed,
           "wrong_msgs": len(wrong), "wrong_rate": round(len(wrong) / max(1, placed), 3),
           "missed": len(missed), "missed_rate": round(len(missed) / max(1, n_exp), 3), "spurious": len(spur)}
    if show:
        res["wrong"] = [{"text": t[:160], "got": b, "expected": e} for t, b, e in wrong]
        res["missed_list"] = [t[:160] for t in missed]
        res["spurious_list"] = [{"text": t[:160], "got": g} for t, g in spur]
    return res


if __name__ == "__main__":
    r = run("--show" in sys.argv)
    print(json.dumps(r, ensure_ascii=False, indent=1))
