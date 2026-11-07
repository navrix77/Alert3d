"""Дані для самоаналізу без доступу до ПК і до сайту: знімок публічних адрес sky.navryx.com.ua, який GitHub Actions
щодня кладе в гілку night-data (.github/workflows/night-data.yml).

    python3 scripts/night_fetch.py            # → data/night/: усі файли знімка + brain.sqlite (таблиця msg) + journal.json
    python3 scripts/selfcheck.py data/night/brain.sqlite --days 1 --out data/night/selfcheck_local.json
    python3 scripts/backtest.py data/night/journal.json

Журнал API віддає щонайбільше 5000 записів на запит, тому знімок містить і вибірки за видом (journal_track.json …):
тут їх зливаємо без дублів. Стовпця track у публічному журналі немає (None).
"""
from __future__ import annotations

import io
import json
import sqlite3
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "night"


def main() -> None:
    subprocess.run(["git", "fetch", "-q", "origin", "night-data"], cwd=ROOT, check=True)
    OUT.mkdir(parents=True, exist_ok=True)
    tar = subprocess.run(["git", "archive", "origin/night-data"], cwd=ROOT, check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(tar)) as tf:
        for m in tf.getmembers():
            if m.isfile() and ".." not in m.name and not m.name.startswith("/"):
                tf.extract(m, OUT, filter="data")
    rows: dict[tuple, tuple] = {}
    for f in sorted(OUT.glob("journal*.json")):
        try:
            items = json.loads(f.read_text(encoding="utf-8")).get("items") or []
        except Exception as e:  # noqa: BLE001
            print(f"пропущено {f.name}: {e}", file=sys.stderr)
            continue
        for it in items:
            k = (it.get("t"), it.get("src"), it.get("link"), it.get("text"))
            rows[k] = (it.get("t"), it.get("src"), it.get("link"), it.get("kind"), it.get("type"), it.get("places"), None, it.get("text"))
    data = sorted(rows.values(), key=lambda r: r[0] or 0)
    (OUT / "journal.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    db = OUT / "brain.sqlite"
    db.unlink(missing_ok=True)
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE msg(t REAL, src TEXT, link TEXT, kind TEXT, type TEXT, cnt INT, places TEXT, track TEXT, text TEXT)")
    c.executemany("INSERT INTO msg(t,src,link,kind,type,places,track,text) VALUES(?,?,?,?,?,?,?,?)", data)
    c.commit()
    taken = (OUT / "taken.txt").read_text().strip() if (OUT / "taken.txt").exists() else "?"
    vis = {}
    if (OUT / "visits.json").exists():
        try:
            vis = json.loads((OUT / "visits.json").read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    span = (data[-1][0] - data[0][0]) / 3600 if data else 0
    print(f"night-data {taken}: повідомлень {len(data)} за {span:.0f} год → {db}")
    if vis.get("days"):
        last = vis["days"][-2:] if len(vis["days"]) > 1 else vis["days"]
        print("відвідувачі:", ", ".join(f"{d['day']}: {d['visitors']}" for d in last), "| push-пристроїв:", vis.get("push_devices"))


if __name__ == "__main__":
    main()
