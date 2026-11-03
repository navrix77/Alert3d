"""Щоденний самоаналіз NAVRYX (для рутини й вручну): докази для виправлень і метрики якості.

    python scripts/selfcheck.py [data/brain.sqlite] [--days 3] [--out data/selfcheck.json]

Що робить (лише читає базу, нічого не змінює):
1. Падіння парсера на реальних повідомленнях доби (кожне — втрачене повідомлення).
2. Підозрілі розбори: пункт-тезка далеко від області, яку назвав сам текст; однослівні «села» зі звичайних слів
   (слово з малої літери в середині речення не ловимо — дивимось на ті, що часто повторюються в різних каналах).
3. Бектест прогнозу на журналі (scripts/backtest.py): похибка курсу, влучання «ймовірно далі», проти наївного.
4. Аналітична довідка (app/analyst.py) на кінець періоду.
Результат — JSON з прикладами (джерело + текст + час), на які можна спиратися при виправленнях.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("PYTEST_CURRENT_TEST", "selfcheck")


def kyiv(t: float) -> str:
    return datetime.datetime.fromtimestamp(t, datetime.timezone(datetime.timedelta(hours=2))).strftime("%d.%m %H:%M")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("db", nargs="?", default=str(ROOT / "data" / "brain.sqlite"))
    ap.add_argument("--days", type=float, default=3, help="скільки діб журналу відтворювати (тест — остання доба)")
    ap.add_argument("--out", default=str(ROOT / "data" / "selfcheck.json"))
    a = ap.parse_args()
    # копія бази: живий сервер тримає її відкритою
    tmp = Path(tempfile.mkdtemp()) / "brain.sqlite"
    for suf in ("", "-wal"):  # -shm не потрібен (і буває заблокований живим сервером)
        if Path(a.db + suf).exists():
            try:
                shutil.copyfile(a.db + suf, str(tmp) + suf)
            except OSError:
                if not suf:
                    raise
    db = sqlite3.connect(tmp)
    t_end = db.execute("SELECT max(t) FROM msg").fetchone()[0]
    rows = db.execute("SELECT t, src, link, kind, type, places, track, text FROM msg WHERE t > ? ORDER BY t",
                      (t_end - a.days * 86400,)).fetchall()
    day = [r for r in rows if r[0] > t_end - 86400]
    from app.geo import oblasts
    from app.parser import Parser
    p = Parser()
    rep: dict = {"period": [kyiv(rows[0][0]), kyiv(t_end)] if rows else None, "messages_day": len(day)}

    # 1-2. падіння і розбори, що суперечать області з тексту
    import re as _re
    crashes, conflicts, words = [], [], collections.defaultdict(list)
    seen = set()
    for t, src, link, kind, typ, pl, track, text in day:
        if not text or (src, text) in seen:
            continue
        seen.add((src, text))
        try:
            for seg in p.segments(text):
                o = p.parse(seg, src)
                # область у тексті — звідки/куди летить («на Черкащину», «з Сумщини»), а не де пункт: не суперечність
                dest = _re.search(r"(на|у|в|до|напрямку|бік|з|із|від)\s+[а-яіїєґ']+(щину|ччину|щини|ччини|щиною|ччиною)", seg.lower())
                if o.oblast_hint and not getattr(p, "_chan_bbox", False) and not dest:
                    for r in o.places:
                        ob = oblasts().of(r.place.lon, r.place.lat)
                        if ob and ob != o.oblast_hint and r.place.kind not in ("M", "K", "R", "D"):
                            conflicts.append({"t": kyiv(t), "src": src, "text": seg[:160], "place": r.place.name, "obl": ob, "hint": o.oblast_hint})
                for r in o.places:
                    if r.place.kind in ("C", "X") and " " not in r.place.name:
                        words[r.place.name].append((kyiv(t), src, seg[:120]))
        except Exception as e:  # noqa: BLE001
            crashes.append({"t": kyiv(t), "src": src, "text": text[:200], "error": f"{type(e).__name__}: {e}"})
    rep["crashes"] = crashes[:30]
    rep["hint_conflicts"] = conflicts[:40]
    # «звичайне слово стало селом»: назва малого пункту, яка в тих самих текстах часто трапляється з МАЛОЇ літери
    # (сили/вектор/більше…) — отже це слово мови, а село знайдено лише через велику літеру на початку речення
    import re as _re
    low = collections.Counter()
    for t, src, link, kind, typ, pl, track, text in day:
        for w in _re.findall(r"(?<![\w])([а-яіїєґ'’]{4,})", text or ""):
            low[w[:-1]] += 1
    cand = []
    for k, v in words.items():
        stem = k.lower()[:-1]
        if low.get(stem, 0) >= 3:  # 03.11: поріг 5 пропускав «Сили оборони»→Сила, «триває»→Тривайли
            cand.append({"place": k, "as_place": len(v), "as_word": low[stem], "channels": len({x[1] for x in v}), "examples": v[:3]})
    rep["word_villages"] = sorted(cand, key=lambda x: -x["as_word"])[:25]

    # 3. бектест прогнозу
    import backtest
    rep["backtest"] = backtest.run(rows, t_end - 86400, verbose=False)

    # 4. аналітична довідка на кінець періоду
    from app.analyst import analyze, journal_groups, source_stats
    g = journal_groups([(r[0], r[1], r[6], r[4], r[7]) for r in rows if r[3] == "track"])
    rep["sources"] = source_stats([x for x in g if x["t0"] > t_end - 86400])[:20]
    Path(a.out).write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Повідомлень за добу: {len(day)}; падінь парсера: {len(crashes)}; суперечностей з областю: {len(conflicts)}")
    print("Прогноз «ймовірно далі» (v2):", rep["backtest"].get("_live_pred_acc"))
    print("Похибка курсу:", rep["backtest"].get("_heading_err", {}).get("ALL"))
    for x in rep["word_villages"][:12]:
        print(f"  слово→село? {x['place']}: як пункт {x['as_place']}×, як звичайне слово {x['as_word']}×; напр. {x['examples'][0]}")
    print("Звіт:", a.out)
    _ = analyze  # довідку на живих даних дає /api/analysis


if __name__ == "__main__":
    main()
