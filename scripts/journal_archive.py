"""Накопичення повного журналу по днях (12.11): знімок night-data щодня перезаписується (72 год), а для перевірки трекінгу
потрібні тижні. Зливає всі journal*.json і src/*.json знімка в архів archive/РРРР-ММ-ДД.json.gz (UTC), без дублів.

    python3 scripts/journal_archive.py <тека знімка> <тека архіву> [днів зберігати=45]
Формат рядка: [t, src, link, kind, type, places, None, text] — як у scripts/backtest.py.
"""
from __future__ import annotations

import datetime
import glob
import gzip
import json
import os
import sys


def main(snap: str, arch: str, keep: int = 45) -> None:
    items = {}
    for f in glob.glob(os.path.join(snap, "journal*.json")) + glob.glob(os.path.join(snap, "src", "*.json")):
        try:
            for i in json.load(open(f, encoding="utf-8")).get("items", []):
                items[(i["t"], i["src"], i.get("link"), i.get("text"))] = i
        except Exception as e:  # noqa: BLE001
            print("пропуск", f, e)
    days: dict = {}
    for i in items.values():
        d = datetime.datetime.fromtimestamp(i["t"], datetime.timezone.utc).strftime("%Y-%m-%d")
        days.setdefault(d, []).append([i["t"], i["src"], i.get("link"), i.get("kind"), i.get("type"), i.get("places"), None, i.get("text")])
    os.makedirs(arch, exist_ok=True)
    for d, rows in sorted(days.items()):
        p = os.path.join(arch, d + ".json.gz")
        old = []
        if os.path.exists(p):
            with gzip.open(p, "rt", encoding="utf-8") as f:
                old = json.load(f)
        merged = {(r[0], r[1], r[2], r[7]): r for r in old}
        for r in rows:
            merged[(r[0], r[1], r[2], r[7])] = r
        out = sorted(merged.values(), key=lambda r: r[0])
        with gzip.open(p, "wt", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
        print(d, "було", len(old), "стало", len(out))
    cut = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=keep)).strftime("%Y-%m-%d")
    for p in glob.glob(os.path.join(arch, "*.json.gz")):
        if os.path.basename(p)[:10] < cut:
            os.remove(p)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 45)
