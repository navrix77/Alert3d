"""Бектест підрахунку цілей проти офіційних підсумків Повітряних сил («збито/подавлено» за ніч).
Запуск: python scripts/count_backtest.py data/brain.sqlite
Для кожної ночі (17:00 → 09:00) відтворює повідомлення через розбір і трекер та порівнює кількість різних цілей
(app/count.py: low / mid / high) з офіційним числом. Збито/подавлено — це приблизно 88 % запущених (припущення)."""
import datetime
import re
import sqlite3
import sys
import time

sys.path.insert(0, ".")
from app.config import SOURCES  # noqa: E402
from app.count import estimate  # noqa: E402
from app.parser import Parser  # noqa: E402
from app.tracker import Tracker  # noqa: E402

DR = {"shahed", "jet", "molniya", "geran5"}
db = sqlite3.connect(f"file:{sys.argv[1] if len(sys.argv) > 1 else 'data/brain.sqlite'}?mode=ro", uri=True)
off = {}
for t, x in db.execute("SELECT t, text FROM msg WHERE text LIKE '%збито/подавлено%' ORDER BY t"):
    m = re.search(r"збито/подавлено\s+(\d+)", x)
    if m:
        off[datetime.date.fromtimestamp(t)] = int(m.group(1))
rows = db.execute("SELECT t, src, link, text FROM msg ORDER BY t").fetchall()
p, tr = Parser(), Tracker(SOURCES, learn=False)
seen: dict = {}
nxt = rows[0][0] + 600
for t, src, link, text in rows:
    try:
        o = p.parse(text, src)
        o.raw = text
        tr.ingest(o, src, t, link)
    except Exception:  # noqa: BLE001
        pass
    if t >= nxt:
        for x in tr.snapshot(t)["tracks"]:
            d = seen.setdefault(x["id"], {"type": x["type"], "t0": t, "p0": (x["lat"], x["lon"])})
            d["t1"], d["p1"] = t, (x["lat"], x["lon"])
        nxt = t + 600
print("ніч        офіційно  запущено≈  оцінка low / mid / high")
for day, o in sorted(off.items()):
    end = datetime.datetime(day.year, day.month, day.day, 9).timestamp()
    fr = [v for v in seen.values() if end - 16 * 3600 <= v["t0"] < end and v["type"] in DR]
    e = estimate(fr)["total"]
    print(day, f"{o:8d} {round(o / 0.88):10d}   {e['low']} / {e['mid']} / {e['high']}")
