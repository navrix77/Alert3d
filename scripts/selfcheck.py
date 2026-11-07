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

    # 2б. (03.11) пункт далеко від області регіонального каналу: тезка (Данилівка в Криму з харківського каналу)
    from app.config import CHANNEL_REGION
    from app.geo import dist_km, phon
    obl = oblasts()
    far = []
    for t, src, link, kind, typ, pl, track, text in day:
        reg = CHANNEL_REGION.get(src)
        if not reg or not text or "щин" in (text or "").lower():
            continue
        try:
            for seg in p.segments(text):
                for r in p.parse(seg, src).places:
                    ob = obl.of(r.place.lon, r.place.lat)
                    if ob and ob != reg and not reg.startswith(ob[:5]):
                        far.append({"t": kyiv(t), "src": src, "reg": reg, "place": r.place.name, "obl": ob, "text": seg[:140]})
        except Exception:  # noqa: BLE001
            pass
    rep["far_from_channel"] = far[:40]

    # 2в. (03.11) місцеві назви й скорочення, яких SKY не знає: слово з великої або АБРЕВІАТУРА після «на/над/курс/від/…»
    # у регіональному каналі, з якого не вийшло жодного пункту. Кандидати на словник (як «БД», «МД», «Пісочин»)
    unk = collections.Counter()
    unk_ex = {}
    for t, src, link, kind, typ, pl, track, text in day:
        reg = CHANNEL_REGION.get(src)
        if not reg or not text:
            continue
        try:
            got = {phon(r.place.name)[:4] for seg in p.segments(text) for r in p.parse(seg, src).places}
        except Exception:  # noqa: BLE001
            continue
        for m in _re.finditer(r"(?:на|над|курс(?:ом)?(?:\s+на)?|в\s+район[еі]|біля|около|от|від|через|повз|мимо|/)\s*([А-ЯІЇЄҐ][\w'’\-]+)", text):
            w = m.group(1)
            if phon(w)[:4] in got or len(w) < 2 or _re.search(r"(?i)щин|ччин|чин[іиу]|област|бпла|шахед|^схі", w):
                continue
            unk[(reg, w)] += 1
            unk_ex.setdefault((reg, w), (kyiv(t), src, text[:120]))
    rep["unknown_local_names"] = [{"reg": k[0], "word": k[1], "n": n, "example": unk_ex[k]} for k, n in unk.most_common(40) if n >= 2]

    # 2г. (03.11) неможливий рух: та сама ціль між двома названими позиціями швидше за ~2,5× швидкості типу
    # (так виглядає «стрибок» шахеда з півночі в центр міста або злиття різних цілей)
    from app.tracker import TYPES as _T
    last, jumps = {}, []
    for t, src, link, kind, typ, pl, track, text in day:
        # балістика: «позиція» в каналах це названа ЦІЛЬ залпу, а не місце ракети (07.11: Київ ↔ Бровари ↔ Трипілля за хвилину)
        if not track or not pl or typ not in _T or typ == "ballistic":
            continue
        try:
            pts = [x for x in json.loads(pl) if x.get("r") == "p"]
        except Exception:  # noqa: BLE001
            continue
        if not pts:
            continue
        # той самий пункт, який обрав парсер (тезки!): перший у газетирі «Запоріжжя» з 15 — не місто, звідси
        # 29 з 30 «неможливих» рухів 06.11 (Чернігів → Куликівка «714 км» замість 28)
        try:
            got = [r.place for seg in p.segments(text or "") for r in p.parse(seg, src).places if r.place.name == pts[0]["n"]]
        except Exception:  # noqa: BLE001
            got = []
        if not got:
            continue
        P0 = got[0]
        if track in last:
            t0, q, s0 = last[track]
            dt = max(60.0, t - t0)
            v = dist_km(q.xy, P0.xy) / dt * 3600
            if v > _T[typ]["speed"] * 2.5 and dist_km(q.xy, P0.xy) > 25:
                jumps.append({"track": track, "type": typ, "from": q.name, "to": P0.name, "km": round(dist_km(q.xy, P0.xy)),
                              "min": round(dt / 60, 1), "src": src, "t": kyiv(t), "text": (text or "")[:120]})
        last[track] = (t, P0, src)
    rep["impossible_moves"] = jumps[:30]

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
    print(f"Пунктів поза областю каналу: {len(far)}; невідомих місцевих назв (≥2): {len(rep['unknown_local_names'])}; неможливих переміщень: {len(jumps)}")
    for x in rep["unknown_local_names"][:10]:
        print(f"  невідома назва? {x['reg']}: «{x['word']}» ×{x['n']}; напр. {x['example']}")
    print("Звіт:", a.out)
    _ = analyze  # довідку на живих даних дає /api/analysis


if __name__ == "__main__":
    main()
